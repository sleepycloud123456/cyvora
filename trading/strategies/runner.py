"""Evaluate running paper strategies and submit through the existing broker.

Shield, idempotency, and the kill-switch hook stay in force. A signal below
the recorded profile threshold never becomes an order. Candle volume is not
treated as depth: an unpriced bar is refused by the broker.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Protocol

from backtesting.broker import BrokerCommand, PaperBroker
from backtesting.history import HistoricalSeries
from backtesting.strategies import (
    BreakoutStrategy,
    MomentumStrategy,
    SignalStrategy,
    StrategyIntent,
    StrategyView,
    strategy_by_name,
)
from domain.enums import ExecutionMode
from domain.exceptions import TradingDisabled, TradingValidationError
from domain.simulation import FeeSchedule, HistoricalBar, HistoricalDataset, LatencyModel
from domain.trading import OrderRecord, OrderSide, SolanaInstrument, StrategyAudit, StrategyState
from terminal.profiles import _threshold
from trading.store import TradingStore

HARD_MAX_ORDERS = 8
HARD_WINDOW_SECONDS = 3600
HARD_MAX_BASE = Decimal(1000)
HARD_MAX_NOTIONAL = Decimal(250)
_FEE = FeeSchedule("configured", Decimal(0), Decimal("0.001"))
_LATENCY = LatencyModel(0, 120)


class AuditLog(Protocol):
    """The runner's audit store. Implementations must not log secrets."""

    def append(self, row: StrategyAudit) -> None:
        """Store one evaluation."""
        ...

    def submitted_since(self, strategy_id: str, since: datetime) -> int:
        """Count submitted rows at or after ``since``."""
        ...


class DatasetSource(Protocol):
    """Read one stored series. A missing dataset stays missing."""

    def get_dataset(self, dataset_id: str) -> HistoricalDataset | None:
        """Return the series, or None when it is not stored."""
        ...


class EvaluationSummary:
    """Counts from one pass. The detail is safe to print."""

    def __init__(
        self,
        status: str,
        evaluated: int,
        submitted: int,
        skipped: int,
        refused: int,
        detail: str,
    ) -> None:
        self.status = status
        self.evaluated = evaluated
        self.submitted = submitted
        self.skipped = skipped
        self.refused = refused
        self.detail = detail


def evaluate_running_strategies(
    *,
    mode: ExecutionMode,
    store: TradingStore,
    datasets: DatasetSource,
    audits: AuditLog,
    threshold: str | None,
    now: datetime,
    entries_blocked: Callable[[], bool],
    strategy_id: str | None = None,
) -> EvaluationSummary:
    """Evaluate RUNNING strategies. Read-only mode stores no order."""

    if mode is not ExecutionMode.PAPER:
        return EvaluationSummary(
            "skipped",
            0,
            0,
            0,
            0,
            "Read-only mode does not evaluate paper strategies. Live trading stays locked.",
        )
    parsed_threshold, threshold_reason = _parsed_threshold(threshold)
    running = [
        item
        for item in store.snapshot().strategies
        if item.state is StrategyState.RUNNING
        and (strategy_id is None or item.strategy_id == strategy_id)
    ]
    if not running:
        return EvaluationSummary(
            "ok",
            0,
            0,
            0,
            0,
            "No running paper strategy was evaluated. Live trading stays locked.",
        )
    broker = PaperBroker(
        mode,
        store,
        lambda: now,
        _FEE,
        _LATENCY,
        participation=Decimal("0.02"),
        impact_cap=Decimal("0.02"),
        entries_blocked=entries_blocked,
    )
    submitted = 0
    skipped = 0
    refused = 0
    for strategy in running:
        outcome = _one(
            broker,
            store,
            datasets,
            audits,
            strategy.strategy_id,
            dict(strategy.parameters),
            parsed_threshold,
            threshold_reason,
            now,
            entries_blocked,
        )
        if outcome == "submitted":
            submitted += 1
        elif outcome == "refused" or outcome == "blocked":
            refused += 1
        else:
            skipped += 1
    return EvaluationSummary(
        "ok",
        len(running),
        submitted,
        skipped,
        refused,
        (
            f"Evaluated {len(running)}. Submitted {submitted}. "
            f"Skipped {skipped}. Refused {refused}. "
            "Orders go through Shield. Live trading stays locked."
        ),
    )


def _one(
    broker: PaperBroker,
    store: TradingStore,
    datasets: DatasetSource,
    audits: AuditLog,
    strategy_id: str,
    parameters: Mapping[str, str],
    threshold: Decimal | None,
    threshold_reason: str | None,
    now: datetime,
    entries_blocked: Callable[[], bool],
) -> str:
    dataset_id = parameters.get("dataset_id", "").strip()
    mint = parameters.get("mint", "").strip()
    if not dataset_id or not mint:
        _write(audits, strategy_id, "skipped", "dataset_or_mint_missing", None, None, None, now)
        return "skipped"
    dataset = datasets.get_dataset(dataset_id)
    if dataset is None:
        _write(audits, strategy_id, "skipped", "dataset_missing", None, None, None, now)
        return "skipped"
    try:
        series = HistoricalSeries(dataset)
        model = strategy_by_name(parameters.get("model", "momentum"), parameters)
        quantity = _decimal(parameters.get("quantity"), "Quantity")
        equity = _optional_decimal(parameters.get("equity_quote"), "Equity")
        sol_balance = _optional_decimal(parameters.get("sol_balance"), "SOL balance")
        instrument = _instrument(parameters, mint)
        max_orders, window, max_base, max_notional = _limits(parameters)
    except TradingValidationError as exc:
        _write(audits, strategy_id, "skipped", _short(str(exc)), None, _text(threshold), None, now)
        return "skipped"
    visible = [bar for bar in series.bars(mint) if bar.observed_at <= now]
    if not visible:
        _write(audits, strategy_id, "skipped", "no_bar", None, _text(threshold), None, now)
        return "skipped"
    bar = visible[-1]
    position = next((item for item in store.list_positions() if item.mint == mint), None)
    held = Decimal(0) if position is None else position.quantity
    view = StrategyView(
        mint=mint,
        decided_at=bar.observed_at,
        bars=series.visible(mint, bar.observed_at),
        signals=tuple(item for item in dataset.signals if item.observed_at <= bar.observed_at),
        position_quantity=held,
    )
    intent = model.on_bar(view)
    strength = _strength(model, view, intent)
    if threshold_reason is not None:
        _write(audits, strategy_id, "skipped", threshold_reason, _text(strength), None, None, now)
        return "skipped"
    assert threshold is not None
    if intent is None or intent.side is not OrderSide.BUY:
        exits = _maintain(broker, audits, strategy_id, instrument, bar, equity, sol_balance, now)
        if exits:
            return "submitted"
        _write(
            audits,
            strategy_id,
            "skipped",
            "no_entry_signal",
            _text(strength),
            _text(threshold),
            None,
            now,
        )
        return "skipped"
    if strength < threshold:
        _write(
            audits,
            strategy_id,
            "skipped",
            "below_signal_threshold",
            _text(strength),
            _text(threshold),
            None,
            now,
        )
        return "skipped"
    if quantity > max_base or _notional(quantity, bar) > max_notional:
        _write(
            audits,
            strategy_id,
            "refused",
            "size_limit",
            _text(strength),
            _text(threshold),
            None,
            now,
        )
        return "refused"
    since = now - timedelta(seconds=window)
    if audits.submitted_since(strategy_id, since) >= max_orders:
        _write(
            audits,
            strategy_id,
            "skipped",
            "rate_limit",
            _text(strength),
            _text(threshold),
            None,
            now,
        )
        return "skipped"
    if entries_blocked():
        _write(
            audits,
            strategy_id,
            "blocked",
            "entries_blocked",
            _text(strength),
            _text(threshold),
            None,
            now,
        )
        return "blocked"
    key = _order_key(strategy_id, bar)
    existing = _existing(store, key)
    if existing is not None:
        _write(
            audits,
            strategy_id,
            "duplicate",
            "idempotency_key_already_stored",
            _text(strength),
            _text(threshold),
            existing.client_order_id,
            now,
        )
        return "duplicate"
    command = BrokerCommand(
        strategy_id=strategy_id,
        instrument=instrument,
        side=OrderSide.BUY,
        quantity=quantity,
        bar=bar,
        exit_kind=intent.exit_kind,
        stop_fraction=intent.stop_fraction,
        signal_ref=intent.signal_ref,
        idempotency_key=key,
        narrative=model.narrative,
        equity_quote=equity,
        sol_balance=sol_balance,
        marks=(),
    )
    try:
        result = broker.execute(command)
    except TradingDisabled:
        _write(
            audits,
            strategy_id,
            "blocked",
            "entries_blocked",
            _text(strength),
            _text(threshold),
            None,
            now,
        )
        return "blocked"
    except TradingValidationError as exc:
        _write(
            audits,
            strategy_id,
            "refused",
            _short(str(exc)),
            _text(strength),
            _text(threshold),
            None,
            now,
        )
        return "refused"
    if result.order is None:
        _write(
            audits,
            strategy_id,
            "refused",
            _short(result.refusal or "unpriced"),
            _text(strength),
            _text(threshold),
            None,
            now,
        )
        return "refused"
    _write(
        audits,
        strategy_id,
        "submitted",
        "shield_path",
        _text(strength),
        _text(threshold),
        result.order.client_order_id,
        now,
    )
    return "submitted"


def _maintain(
    broker: PaperBroker,
    audits: AuditLog,
    strategy_id: str,
    instrument: SolanaInstrument,
    bar: HistoricalBar,
    equity: Decimal | None,
    sol_balance: Decimal | None,
    now: datetime,
) -> int:
    key = _order_key(strategy_id, bar) + "x"
    try:
        results = broker.maintain(
            bar,
            instrument,
            equity_quote=equity,
            sol_balance=sol_balance,
            marks=(),
            idempotency_key=key,
        )
    except TradingDisabled:
        _write(audits, strategy_id, "blocked", "entries_blocked", None, None, None, now)
        return 0
    count = 0
    for result in results:
        if result.order is None:
            continue
        count += 1
        _write(
            audits,
            strategy_id,
            "submitted",
            "exit_through_shield",
            None,
            None,
            result.order.client_order_id,
            now,
        )
    return count


def _parsed_threshold(value: str | None) -> tuple[Decimal | None, str | None]:
    try:
        parsed = _threshold(value)
    except TradingValidationError:
        return None, "signal_threshold_invalid"
    if parsed is None:
        return None, "signal_threshold_not_configured"
    return Decimal(parsed), None


def _limits(parameters: Mapping[str, str]) -> tuple[int, int, Decimal, Decimal]:
    orders = _bounded_int(parameters.get("max_orders"), HARD_MAX_ORDERS, HARD_MAX_ORDERS)
    window = _bounded_int(
        parameters.get("window_seconds"), HARD_WINDOW_SECONDS, HARD_WINDOW_SECONDS
    )
    base = _bounded_decimal(parameters.get("max_base_quantity"), HARD_MAX_BASE, HARD_MAX_BASE)
    notional = _bounded_decimal(
        parameters.get("max_quote_notional"), HARD_MAX_NOTIONAL, HARD_MAX_NOTIONAL
    )
    return orders, window, base, notional


def _bounded_int(raw: str | None, default: int, hard: int) -> int:
    if raw is None or raw.strip() == "":
        return min(default, hard)
    if not raw.strip().isdecimal():
        raise TradingValidationError("A limit must be a whole number.")
    value = int(raw.strip())
    if value < 1:
        raise TradingValidationError("A limit must be at least 1.")
    return min(value, hard)


def _bounded_decimal(raw: str | None, default: Decimal, hard: Decimal) -> Decimal:
    if raw is None or raw.strip() == "":
        return min(default, hard)
    value = _decimal(raw, "Limit")
    if value <= 0:
        raise TradingValidationError("A size limit must be positive.")
    return min(value, hard)


def _decimal(raw: str | None, label: str) -> Decimal:
    if raw is None or raw.strip() == "":
        raise TradingValidationError(f"{label} is required.")
    try:
        value = Decimal(raw.strip())
    except InvalidOperation as exc:
        raise TradingValidationError(f"{label} must be a decimal.") from exc
    if not value.is_finite() or value <= 0:
        raise TradingValidationError(f"{label} must be a positive decimal.")
    return value


def _optional_decimal(raw: str | None, label: str) -> Decimal | None:
    if raw is None or raw.strip() == "":
        return None
    return _decimal(raw, label)


def _instrument(parameters: Mapping[str, str], mint: str) -> SolanaInstrument:
    symbol = parameters.get("symbol", "TOKEN").strip() or "TOKEN"
    return SolanaInstrument(
        mint,
        symbol[:32],
        _decimals(parameters.get("size_decimals"), "Size decimals"),
        _decimals(parameters.get("price_decimals"), "Price decimals"),
        (parameters.get("quote_symbol") or "SOL").strip() or "SOL",
        _decimals(parameters.get("quote_decimals"), "Quote decimals"),
    )


def _decimals(raw: str | None, label: str) -> int:
    if raw is None or raw.strip() == "":
        raise TradingValidationError(f"{label} is required.")
    if not raw.strip().isdecimal():
        raise TradingValidationError(f"{label} must be a whole number.")
    value = int(raw.strip())
    if value < 0 or value > 12:
        raise TradingValidationError(f"{label} must be from 0 through 12.")
    return value


def _strength(
    strategy: MomentumStrategy | BreakoutStrategy | SignalStrategy,
    view: StrategyView,
    intent: StrategyIntent | None,
) -> Decimal:
    if intent is None or intent.side is not OrderSide.BUY:
        return Decimal(0)
    if isinstance(strategy, SignalStrategy):
        return Decimal(1)
    if isinstance(strategy, MomentumStrategy):
        closes = [bar.close for bar in view.bars if bar.close is not None and bar.close > 0]
        if len(closes) <= strategy.lookback:
            return Decimal(0)
        previous = closes[-1 - strategy.lookback]
        change = (closes[-1] - previous) / previous
        if change <= 0:
            return Decimal(0)
        return min(change, Decimal(1))
    close = view.bars[-1].close if view.bars else None
    if close is None or len(view.bars) <= strategy.lookback:
        return Decimal(0)
    highs: list[Decimal] = []
    for bar in view.bars[-1 - strategy.lookback : -1]:
        high = bar.high if bar.high is not None else bar.close
        if high is None or high <= 0:
            return Decimal(0)
        highs.append(high)
    if not highs:
        return Decimal(0)
    prior = max(highs)
    if prior <= 0 or close <= prior:
        return Decimal(0)
    return min((close - prior) / prior, Decimal(1))


def _notional(quantity: Decimal, bar: HistoricalBar) -> Decimal:
    mark = bar.close
    if mark is None or mark <= 0:
        if bar.base_reserve and bar.quote_reserve and bar.base_reserve > 0:
            mark = bar.quote_reserve / bar.base_reserve
        else:
            return HARD_MAX_NOTIONAL + 1
    return quantity * mark


def _order_key(strategy_id: str, bar: HistoricalBar) -> str:
    digest = hashlib.sha256(strategy_id.encode("utf-8")).hexdigest()[:16]
    return f"ps.{digest}.{int(bar.observed_at.timestamp())}"


def _existing(store: TradingStore, key: str) -> OrderRecord | None:
    for order in store.list_orders():
        if order.idempotency_key == key:
            return order
    return None


def _write(
    audits: AuditLog,
    strategy_id: str,
    action: str,
    reason: str,
    strength: str | None,
    threshold: str | None,
    client_order_id: str | None,
    now: datetime,
) -> None:
    audits.append(
        StrategyAudit(
            strategy_id=strategy_id,
            action=action,
            reason=_short(reason),
            signal_strength=strength,
            threshold=threshold,
            client_order_id=client_order_id,
            created_at=now,
            live_trading_enabled=False,
        )
    )


def _text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value.quantize(Decimal("0.00000001")))


def _short(value: str) -> str:
    cleaned = " ".join(value.split())
    return cleaned[:240]
