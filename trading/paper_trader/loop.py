"""One paper-trader pass over stored radar candidates and open positions.

Entries and exits are priced by PaperBroker, which submits through Shield
and PaperExecutionGateway. A radar score does not approve an order. Candle
close is not a fill: a pool without reserves is refused.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from backtesting.broker import BrokerCommand, BrokerResult, PaperBroker
from domain.enums import ExecutionMode
from domain.exceptions import TradingDisabled, TradingValidationError
from domain.paper_trader import (
    STRATEGY_ID,
    PoolQuote,
    RadarCandidate,
    TraderDecision,
    TraderTick,
)
from domain.shield import PAPER_APPROVED, CampaignRecord
from domain.simulation import FeeSchedule, HistoricalBar, LatencyModel
from domain.trading import OrderRecord, OrderSide, PositionRecord, SolanaInstrument
from shield.numbers import quantize_down
from trading.execution.gateway import PaperExecutionGateway
from trading.instruments import require_mint, require_symbol
from trading.portfolio.accounting import unrealized_pnl
from trading.store import TradingStore
from trading.strategies.manager import StrategyManager

_FEE = FeeSchedule("configured", Decimal(0), Decimal("0.001"))
_LATENCY = LatencyModel(0, 120)
_SIZE_DECIMALS = 6
_PRICE_DECIMALS = 9
_QUOTE_DECIMALS = 9
_ENTRY_LIFECYCLES = frozenset({"watch_suggested", "ranked"})
_FRESH_OK = frozenset({"fresh", "live_quote"})
_CLEAR = "APPROVED_FOR_FURTHER_ANALYSIS"
_RISKY = frozenset({"CAUTION", "HIGH_RISK", "UNKNOWN"})


def _security_ok(category: str | None) -> bool:
    """Paper only: optionally treat CAUTION/HIGH_RISK/UNKNOWN as tradeable. REJECTED never is."""
    if category == _CLEAR:
        return True
    return category in _RISKY and _allow_risky()


def _allow_risky() -> bool:
    from config.settings import get_settings

    return get_settings().paper_allow_risky_security


_ORDER_BLOCKS = frozenset({"kill_switch", "kill_switch_unreadable", "entries_blocked"})


@dataclass(frozen=True)
class _Book:
    cash: Decimal
    equity: Decimal
    marked: Decimal
    realized: Decimal
    unrealized: Decimal
    marks: tuple[tuple[str, Decimal], ...]


def run_once(
    *,
    mode: ExecutionMode,
    store: TradingStore,
    candidates: tuple[RadarCandidate, ...],
    quotes: dict[str, PoolQuote],
    cycle_id: int | None,
    quotes_fresh: bool,
    bankroll: Decimal,
    per_trade_fraction: Decimal,
    max_exposure_fraction: Decimal,
    min_score: Decimal,
    stop_fraction: Decimal,
    max_entries: int,
    max_quote_age_seconds: int,
    now: datetime,
    entries_blocked: bool,
    halt_entries: bool,
    kill_switch: str,
    unpriced_writeoff_seconds: int = 1800,
    last_priced_at: Mapping[str, datetime] | None = None,
    require_price_feed: bool = True,
    feed_marks: Mapping[str, PoolQuote] | None = None,
    max_mark_age_seconds: int | None = None,
    min_liquidity_usd: Decimal = Decimal(0),
) -> TraderTick:
    """Evaluate candidates and due exits. Read-only mode stores no order."""

    if mode is not ExecutionMode.PAPER:
        return _tick(
            "skipped",
            kill_switch,
            halt_entries,
            entries_blocked,
            0,
            (),
            None,
            "Read-only mode does not run the paper trader. Live trading stays locked.",
            now,
            store,
            quotes,
            bankroll,
            max_quote_age_seconds,
        )
    gate = _gate_reason(kill_switch, entries_blocked, halt_entries)
    status = _status(gate)
    mark_age = max_quote_age_seconds if max_mark_age_seconds is None else max_mark_age_seconds
    opened = False
    try:
        _open_strategy(store, now)
        opened = True
        broker = PaperBroker(
            mode,
            store,
            lambda: now,
            _FEE,
            _LATENCY,
            participation=Decimal("0.02"),
            impact_cap=Decimal("0.02"),
            entries_blocked=lambda: gate in _ORDER_BLOCKS,
        )
        decisions: list[TraderDecision] = []
        priced_times = dict(last_priced_at or {})
        decisions.extend(
            _writeoffs(
                broker,
                store,
                quotes,
                now,
                mark_age,
                unpriced_writeoff_seconds,
                priced_times,
                gate,
            )
        )
        decisions.extend(
            _exits(
                broker,
                store,
                quotes,
                now,
                bankroll,
                mark_age,
                gate,
            )
        )
        submitted_entries = 0
        ordered = sorted(candidates, key=lambda item: (-(item.score or Decimal(-1)), item.mint))
        for candidate in ordered:
            decision, took = _entry(
                broker,
                store,
                candidate,
                quotes,
                cycle_id,
                quotes_fresh,
                bankroll,
                per_trade_fraction,
                max_exposure_fraction,
                min_score,
                stop_fraction,
                max_entries,
                submitted_entries,
                max_quote_age_seconds,
                mark_age,
                now,
                gate,
                require_price_feed,
                feed_marks,
                min_liquidity_usd,
            )
            decisions.append(decision)
            if took:
                submitted_entries += 1
        detail = _detail(len(candidates), decisions, kill_switch, entries_blocked)
        return _tick(
            status,
            kill_switch,
            halt_entries,
            entries_blocked,
            len(candidates),
            tuple(decisions),
            _book(store, quotes, bankroll, now, mark_age),
            detail,
            now,
            store,
            quotes,
            bankroll,
            max_quote_age_seconds,
        )
    finally:
        if opened:
            _close_strategy(store, now)


def _entry(
    broker: PaperBroker,
    store: TradingStore,
    candidate: RadarCandidate,
    quotes: dict[str, PoolQuote],
    cycle_id: int | None,
    quotes_fresh: bool,
    bankroll: Decimal,
    per_trade_fraction: Decimal,
    max_exposure_fraction: Decimal,
    min_score: Decimal,
    stop_fraction: Decimal,
    max_entries: int,
    submitted_entries: int,
    max_quote_age_seconds: int,
    max_mark_age_seconds: int,
    now: datetime,
    gate: str | None,
    require_price_feed: bool,
    feed_marks: Mapping[str, PoolQuote] | None,
    min_liquidity_usd: Decimal,
) -> tuple[TraderDecision, bool]:
    symbol = _safe_symbol(candidate.symbol)
    score = _score_text(candidate.score)
    reason = _filter_reason(candidate, min_score, min_liquidity_usd)
    if reason is None and not quotes_fresh:
        reason = "stale_cycle"
    if reason is None and cycle_id is None:
        reason = "no_radar_cycle"
    mint = candidate.mint
    try:
        mint = require_mint(candidate.mint)
    except TradingValidationError:
        return _decision(candidate.mint[:64], symbol, "refused", "invalid_mint", score, None), False
    if reason is not None:
        return _decision(mint, symbol, "refused", reason, score, None), False
    if _open_quantity(store, mint) > 0:
        return _decision(mint, symbol, "held", "position_open", score, None), False
    if gate is not None:
        return _decision(mint, symbol, "blocked", gate, score, None), False
    if submitted_entries >= max_entries:
        return _decision(mint, symbol, "skipped", "entry_limit", score, None), False
    book = _book(store, quotes, bankroll, now, max_mark_age_seconds)
    if book is None:
        return _decision(mint, symbol, "refused", "exposure_unpriced", score, None), False
    if book.cash < 0:
        return _decision(mint, symbol, "refused", "bankroll_exhausted", score, None), False
    quote = quotes.get(mint)
    spot = _spot(quote)
    if quote is None or spot is None or not _fresh(quote, now, max_quote_age_seconds):
        return _decision(mint, symbol, "refused", "pool_reserves_missing", score, None), False
    if require_price_feed and not _price_feed_ok(
        None if feed_marks is None else feed_marks.get(mint),
        spot,
        now,
        max_mark_age_seconds,
    ):
        return _decision(mint, symbol, "refused", "no_price_feed", score, None), False
    room = bankroll * max_exposure_fraction - book.marked
    if room <= 0:
        return _decision(mint, symbol, "refused", "exposure_cap", score, None), False
    trade_notional = min(bankroll * per_trade_fraction, room, book.cash)
    quantity = quantize_down(trade_notional / spot, _SIZE_DECIMALS)
    if quantity <= 0:
        return _decision(mint, symbol, "refused", "size_below_precision", score, None), False
    if cycle_id is None:
        return _decision(mint, symbol, "refused", "no_radar_cycle", score, None), False
    key = _entry_key(mint, cycle_id)
    existing = _existing(store, key)
    if existing is not None:
        return (
            _decision(
                mint,
                symbol,
                "duplicate",
                "idempotency_key_already_stored",
                score,
                existing.client_order_id,
            ),
            False,
        )
    bar = _bar(mint, symbol, quote, candidate, now)
    if bar is None:
        return _decision(mint, symbol, "refused", "pool_reserves_missing", score, None), False
    try:
        result = broker.execute(
            _command(
                mint,
                symbol,
                OrderSide.BUY,
                quantity,
                bar,
                "entry",
                stop_fraction,
                "radar-score",
                key,
                book,
            )
        )
    except TradingDisabled:
        return _decision(mint, symbol, "blocked", gate or "entries_blocked", score, None), False
    except TradingValidationError as exc:
        return _decision(mint, symbol, "refused", _short(str(exc)), score, None), False
    return _from_result(mint, symbol, score, result, taken=True)


def _writeoffs(
    broker: PaperBroker,
    store: TradingStore,
    quotes: dict[str, PoolQuote],
    now: datetime,
    max_quote_age_seconds: int,
    unpriced_writeoff_seconds: int,
    last_priced_at: Mapping[str, datetime],
    gate: str | None,
) -> list[TraderDecision]:
    decisions: list[TraderDecision] = []
    if unpriced_writeoff_seconds <= 0:
        return decisions
    for position in store.list_positions():
        if position.quantity <= 0:
            continue
        campaign = _campaign(store.load_shield().campaigns, position.mint)
        if campaign is None or campaign.strategy_id != STRATEGY_ID:
            continue
        if not _writeoff_due(
            position,
            store,
            quotes,
            now,
            max_quote_age_seconds,
            unpriced_writeoff_seconds,
            last_priced_at,
        ):
            continue
        symbol = _symbol_for(store, position.mint)
        if gate in _ORDER_BLOCKS:
            decisions.append(
                _decision(position.mint, symbol, "blocked", gate or "entries_blocked", None, None)
            )
            continue
        key = _writeoff_key(position.mint, position.updated_at)
        existing = _existing(store, key)
        if existing is not None:
            if existing.filled_quantity > 0 and existing.fill_price == Decimal(0):
                decisions.append(
                    _decision(
                        position.mint,
                        symbol,
                        "exited",
                        "unpriced_writeoff",
                        None,
                        existing.client_order_id,
                    )
                )
            else:
                decisions.append(
                    _decision(
                        position.mint,
                        symbol,
                        "refused",
                        _short(existing.reason or "unpriced_writeoff"),
                        None,
                        existing.client_order_id,
                    )
                )
            continue
        try:
            result = broker.write_off(
                _instrument(position.mint, symbol),
                position.quantity,
                strategy_id=STRATEGY_ID,
                idempotency_key=key,
            )
        except TradingDisabled:
            decisions.append(
                _decision(position.mint, symbol, "blocked", gate or "entries_blocked", None, None)
            )
            continue
        except TradingValidationError as exc:
            decisions.append(
                _decision(position.mint, symbol, "refused", _short(str(exc)), None, None)
            )
            continue
        order = result.order
        if order is None or order.shield_decision != PAPER_APPROVED or order.filled_quantity <= 0:
            reason = result.refusal
            if reason is None and order is not None:
                reason = order.reason
            decisions.append(
                _decision(
                    position.mint,
                    symbol,
                    "refused",
                    _short(reason or "unpriced_writeoff"),
                    None,
                    None if order is None else order.client_order_id,
                )
            )
            continue
        decisions.append(
            _decision(
                position.mint,
                symbol,
                "exited",
                "unpriced_writeoff",
                None,
                order.client_order_id,
            )
        )
    return decisions


def _writeoff_due(
    position: PositionRecord,
    store: TradingStore,
    quotes: dict[str, PoolQuote],
    now: datetime,
    max_quote_age_seconds: int,
    unpriced_writeoff_seconds: int,
    last_priced_at: Mapping[str, datetime],
) -> bool:
    mark = _fresh_mark(quotes.get(position.mint), now, max_quote_age_seconds)
    if mark is not None:
        return False
    priced = _last_priced(position, store, last_priced_at)
    if priced is None or now.tzinfo is None or priced.tzinfo is None:
        return False
    return (now - priced).total_seconds() >= unpriced_writeoff_seconds


def _last_priced(
    position: PositionRecord,
    store: TradingStore,
    last_priced_at: Mapping[str, datetime],
) -> datetime | None:
    found: list[datetime] = []
    recorded = last_priced_at.get(position.mint)
    if recorded is not None:
        aware = _aware(recorded)
        if aware is not None:
            found.append(aware)
    updated = _aware(position.updated_at)
    if updated is not None:
        found.append(updated)
    for order in store.list_orders():
        if (
            order.mint == position.mint
            and order.filled_quantity > 0
            and order.fill_price is not None
        ):
            stamp = _aware(order.updated_at)
            if stamp is not None:
                found.append(stamp)
    if not found:
        return None
    return max(found)


def _aware(value: datetime) -> datetime | None:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _writeoff_key(mint: str, updated_at: datetime) -> str:
    digest = hashlib.sha256(mint.encode("utf-8")).hexdigest()[:12]
    return f"pt.{digest}.unpriced-wo.{int(updated_at.timestamp())}"


def _exits(
    broker: PaperBroker,
    store: TradingStore,
    quotes: dict[str, PoolQuote],
    now: datetime,
    bankroll: Decimal,
    max_quote_age_seconds: int,
    gate: str | None,
) -> list[TraderDecision]:
    decisions: list[TraderDecision] = []
    shield = store.load_shield()
    for position in store.list_positions():
        if position.quantity <= 0:
            continue
        campaign = _campaign(shield.campaigns, position.mint)
        if campaign is None or campaign.strategy_id != STRATEGY_ID:
            continue
        symbol = _symbol_for(store, position.mint)
        if gate in _ORDER_BLOCKS:
            decisions.append(
                _decision(position.mint, symbol, "blocked", gate or "entries_blocked", None, None)
            )
            continue
        quote = quotes.get(position.mint)
        if quote is None or not _fresh(quote, now, max_quote_age_seconds) or _spot(quote) is None:
            reason = "mark_stale" if quote is not None else "mark_missing"
            decisions.append(_decision(position.mint, symbol, "held", reason, None, None))
            continue
        bar = _bar(position.mint, symbol, quote, None, now)
        if bar is None:
            decisions.append(
                _decision(position.mint, symbol, "held", "pool_reserves_missing", None, None)
            )
            continue
        book = _book(store, quotes, bankroll, now, max_quote_age_seconds)
        usable = book is not None and book.cash >= 0
        try:
            results = broker.maintain(
                bar,
                _instrument(position.mint, symbol),
                equity_quote=book.equity if usable and book is not None else None,
                sol_balance=book.cash if usable and book is not None else None,
                marks=book.marks if usable and book is not None else (),
                idempotency_key=_exit_key(position.mint, now),
            )
        except TradingDisabled:
            decisions.append(
                _decision(position.mint, symbol, "blocked", gate or "entries_blocked", None, None)
            )
            continue
        except TradingValidationError as exc:
            decisions.append(
                _decision(position.mint, symbol, "refused", _short(str(exc)), None, None)
            )
            continue
        if not results or all(item.order is None and item.refusal is None for item in results):
            decisions.append(_decision(position.mint, symbol, "held", "within_plan", None, None))
            continue
        for result in results:
            decision, _took = _from_result(position.mint, symbol, None, result, taken=False)
            decisions.append(decision)
    return decisions


def _from_result(
    mint: str,
    symbol: str,
    score: str | None,
    result: BrokerResult,
    *,
    taken: bool,
) -> tuple[TraderDecision, bool]:
    order = result.order
    if order is None:
        return (
            _decision(mint, symbol, "refused", _short(result.refusal or "unpriced"), score, None),
            False,
        )
    if order.shield_decision != PAPER_APPROVED:
        return (
            _decision(
                mint,
                symbol,
                "refused",
                _short(order.reason or "shield_denied"),
                score,
                order.client_order_id,
            ),
            False,
        )
    reason = "shield_path" if taken else "exit_through_shield"
    return _decision(mint, symbol, "submitted", reason, score, order.client_order_id), taken


def _filter_reason(
    candidate: RadarCandidate, min_score: Decimal, min_liquidity: Decimal = Decimal(0)
) -> str | None:
    if candidate.score is None:
        return "score_missing"
    if candidate.score < min_score:
        return "below_score"
    if candidate.lifecycle not in _ENTRY_LIFECYCLES:
        return "lifecycle"
    if not _security_ok(candidate.security_category):
        return "security_not_clear"
    if candidate.freshness not in _FRESH_OK:
        return "stale_candles"
    if candidate.price is None or candidate.price <= 0:
        return "price_missing"
    if not _reserve_pair(candidate.base_reserve, candidate.quote_reserve):
        return "pool_reserves_missing"
    if min_liquidity > 0:
        if candidate.liquidity is None:
            return "liquidity_missing"
        if candidate.liquidity < min_liquidity:
            return "below_liquidity"
    return None


def _book(
    store: TradingStore,
    quotes: dict[str, PoolQuote],
    bankroll: Decimal,
    now: datetime,
    max_quote_age_seconds: int,
) -> _Book | None:
    marked = Decimal(0)
    marks: list[tuple[str, Decimal]] = []
    unrealized = Decimal(0)
    for position in store.list_positions():
        if position.quantity <= 0:
            continue
        mark = _fresh_mark(quotes.get(position.mint), now, max_quote_age_seconds)
        pnl = unrealized_pnl(position, mark)
        if mark is None or pnl is None:
            return None
        marked += position.quantity * mark
        unrealized += pnl
        marks.append((position.mint, mark))
    realized = sum((item.realized_pnl_quote for item in store.list_positions()), Decimal(0))
    equity = bankroll + realized + unrealized
    cash = equity - marked
    return _Book(cash, equity, marked, realized, unrealized, tuple(marks))


def _command(
    mint: str,
    symbol: str,
    side: OrderSide,
    quantity: Decimal,
    bar: HistoricalBar,
    kind: str,
    stop_fraction: Decimal | None,
    signal_ref: str | None,
    key: str,
    book: _Book,
) -> BrokerCommand:
    return BrokerCommand(
        strategy_id=STRATEGY_ID,
        instrument=_instrument(mint, symbol),
        side=side,
        quantity=quantity,
        bar=bar,
        exit_kind=kind,
        stop_fraction=stop_fraction,
        signal_ref=signal_ref,
        idempotency_key=key,
        narrative="radar-paper",
        equity_quote=book.equity,
        sol_balance=book.cash,
        marks=book.marks,
    )


def _bar(
    mint: str,
    symbol: str,
    quote: PoolQuote,
    candidate: RadarCandidate | None,
    now: datetime,
) -> HistoricalBar | None:
    if not _reserve_pair(quote.base_reserve, quote.quote_reserve):
        return None
    assert quote.base_reserve is not None and quote.quote_reserve is not None
    spot = quote.quote_reserve / quote.base_reserve
    age = None
    security = None
    if candidate is not None:
        age = _age(candidate.creation_timestamp, now)
        security = "clear" if _security_ok(candidate.security_category) else None
    return HistoricalBar(
        mint=mint,
        symbol=symbol,
        observed_at=quote.observed_at,
        source="gmgn_pool",
        close=spot,
        base_reserve=quote.base_reserve,
        quote_reserve=quote.quote_reserve,
        security=security,
        token_age_seconds=age,
    )


def _tick(
    status: str,
    kill_switch: str,
    halt_entries: bool,
    entries_blocked: bool,
    candidate_count: int,
    decisions: tuple[TraderDecision, ...],
    book: _Book | None,
    detail: str,
    now: datetime,
    store: TradingStore,
    quotes: dict[str, PoolQuote],
    bankroll: Decimal,
    max_quote_age_seconds: int,
) -> TraderTick:
    del now, quotes, bankroll, max_quote_age_seconds
    submitted = sum(1 for item in decisions if item.action == "submitted")
    refused = sum(1 for item in decisions if item.action == "refused")
    open_count = sum(1 for item in store.list_positions() if item.quantity > 0)
    return TraderTick(
        status=status,
        kill_switch=kill_switch,
        halt_entries=halt_entries,
        entries_blocked=entries_blocked,
        candidate_count=candidate_count,
        submitted_count=submitted,
        refused_count=refused,
        detail=detail,
        decisions=decisions,
        equity_quote=None if book is None else book.equity,
        realized_quote=None if book is None else book.realized,
        unrealized_quote=None if book is None else book.unrealized,
        open_positions=open_count,
    )


def _open_strategy(store: TradingStore, now: datetime) -> None:
    gateway = PaperExecutionGateway(ExecutionMode.PAPER, store, lambda: now)
    manager = StrategyManager(ExecutionMode.PAPER, store, gateway, lambda: now)
    current = store.get_strategy(STRATEGY_ID)
    if current is None:
        manager.register(STRATEGY_ID, "Radar paper", {"source": "radar"})
    elif current.state.value == "RUNNING":
        return
    manager.start(STRATEGY_ID)


def _close_strategy(store: TradingStore, now: datetime) -> None:
    current = store.get_strategy(STRATEGY_ID)
    if current is None or current.state.value != "RUNNING":
        return
    gateway = PaperExecutionGateway(ExecutionMode.PAPER, store, lambda: now)
    manager = StrategyManager(ExecutionMode.PAPER, store, gateway, lambda: now)
    manager.stop(STRATEGY_ID)


def _gate_reason(kill_switch: str, entries_blocked: bool, halt_entries: bool) -> str | None:
    if kill_switch == "engaged":
        return "kill_switch"
    if kill_switch == "unreadable":
        return "kill_switch_unreadable"
    if entries_blocked:
        return "entries_blocked"
    if halt_entries:
        return "shield_paused"
    return None


def _status(gate: str | None) -> str:
    if gate in _ORDER_BLOCKS:
        return "blocked"
    if gate == "shield_paused":
        return "paused"
    return "running"


def _detail(
    candidates: int,
    decisions: list[TraderDecision],
    kill_switch: str,
    entries_blocked: bool,
) -> str:
    submitted = sum(1 for item in decisions if item.action == "submitted")
    refused = sum(1 for item in decisions if item.action == "refused")
    blocked = "true" if entries_blocked else "false"
    return (
        f"Candidates {candidates}. Submitted {submitted}. Refused {refused}. "
        f"Kill switch {kill_switch}. Entries blocked {blocked}. "
        "Orders go through Shield. Live trading stays locked."
    )


def _campaign(campaigns: tuple[CampaignRecord, ...], mint: str) -> CampaignRecord | None:
    return next((item for item in campaigns if item.mint == mint and item.closed_at is None), None)


def _open_quantity(store: TradingStore, mint: str) -> Decimal:
    position = next((item for item in store.list_positions() if item.mint == mint), None)
    if position is None:
        return Decimal(0)
    return position.quantity


def _symbol_for(store: TradingStore, mint: str) -> str:
    for order in reversed(store.list_orders()):
        if order.mint == mint:
            return _safe_symbol(order.symbol)
    return "TOKEN"


def _existing(store: TradingStore, key: str) -> OrderRecord | None:
    for order in store.list_orders():
        if order.idempotency_key == key:
            return order
    return None


def _instrument(mint: str, symbol: str) -> SolanaInstrument:
    return SolanaInstrument(
        mint,
        require_symbol(_safe_symbol(symbol)),
        _SIZE_DECIMALS,
        _PRICE_DECIMALS,
        "SOL",
        _QUOTE_DECIMALS,
    )


def _price_feed_ok(
    mark: PoolQuote | None,
    entry_spot: Decimal,
    now: datetime,
    max_age: int,
) -> bool:
    if entry_spot <= 0:
        return False
    mark_spot = _fresh_mark(mark, now, max_age)
    if mark_spot is None or mark_spot <= 0:
        return False
    return abs(mark_spot - entry_spot) / entry_spot <= Decimal("0.5")


def _fresh(quote: PoolQuote, now: datetime, max_age: int) -> bool:
    if quote.observed_at.tzinfo is None or now.tzinfo is None:
        return False
    return (now - quote.observed_at).total_seconds() <= max_age


def _fresh_mark(quote: PoolQuote | None, now: datetime, max_age: int) -> Decimal | None:
    if quote is None or not _fresh(quote, now, max_age):
        return None
    return _spot(quote)


def _spot(quote: PoolQuote | None) -> Decimal | None:
    if quote is None or not _reserve_pair(quote.base_reserve, quote.quote_reserve):
        return None
    assert quote.base_reserve is not None and quote.quote_reserve is not None
    spot = quote.quote_reserve / quote.base_reserve
    if spot <= 0:
        return None
    return spot


def _reserve_pair(base: Decimal | None, quote: Decimal | None) -> bool:
    return base is not None and quote is not None and base > 0 and quote > 0


def _age(creation: int | None, now: datetime) -> int | None:
    if creation is None or creation <= 0:
        return None
    seconds = int(now.timestamp()) - creation
    if seconds < 0:
        return None
    return seconds


def _entry_key(mint: str, cycle_id: int) -> str:
    digest = hashlib.sha256(mint.encode("utf-8")).hexdigest()[:12]
    return f"pt.{digest}.{cycle_id}"


def _exit_key(mint: str, now: datetime) -> str:
    digest = hashlib.sha256(mint.encode("utf-8")).hexdigest()[:12]
    return f"pt.{digest}.{int(now.timestamp())}x"


def _decision(
    mint: str,
    symbol: str,
    action: str,
    reason: str,
    score: str | None,
    client_order_id: str | None,
) -> TraderDecision:
    return TraderDecision(
        mint=mint[:64],
        symbol=_safe_symbol(symbol),
        action=action,
        reason=_short(reason),
        score=score,
        client_order_id=client_order_id,
        live_trading_enabled=False,
    )


def _safe_symbol(raw: str | None) -> str:
    text = "TOKEN" if raw is None or raw.strip() == "" else raw.strip()
    cleaned = "".join(char for char in text if char.isalnum() or char in "._-")[:32]
    if not cleaned or not cleaned[0].isalnum():
        return "TOKEN"
    return cleaned


def _score_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01")), "f")


def _short(value: str) -> str:
    return " ".join(value.split())[:240]
