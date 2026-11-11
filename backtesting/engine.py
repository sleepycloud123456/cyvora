"""Walk one historical series through Shield and the paper broker.

The book is an in-memory ledger. It is not the operator's paper account.
A strategy sees a bar only at or before the decision. A delayed fill uses a
later observation and never uses the candle close as the price.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from backtesting.broker import BrokerCommand, BrokerResult, PaperBroker, probe_quantity
from backtesting.history import HistoricalSeries, missing_mints
from backtesting.latency import fill_window
from backtesting.performance import measure
from backtesting.strategies import (
    BreakoutStrategy,
    MomentumStrategy,
    SignalStrategy,
    StrategyView,
)
from domain.enums import ExecutionMode
from domain.exceptions import TradingDisabled, TradingValidationError
from domain.simulation import (
    FeeSchedule,
    HistoricalBar,
    HistoricalDataset,
    LatencyModel,
    OrderSummary,
    Refusal,
    SimulationReport,
    StrategySummary,
)
from domain.trading import (
    ExecutionReport,
    OrderRecord,
    OrderSide,
    OrderState,
    SolanaInstrument,
)
from trading.execution.gateway import PaperExecutionGateway
from trading.memory_store import MemoryTradingStore
from trading.strategies.manager import StrategyManager

SimulationStrategy = MomentumStrategy | BreakoutStrategy | SignalStrategy

BASE_LIMITATIONS = (
    "Fills use a constant-product pool or one displayed book level. "
    "Candle close is a mark, not a fill.",
    "A planned stop is not a guaranteed exit.",
    "Optimized parameters are not deployed.",
    "Paper fills are simulated. No chain transaction is submitted.",
    "A missing pool impact is not treated as zero.",
)


@dataclass(frozen=True)
class BacktestSpec:
    """Inputs for one isolated paper run."""

    dataset: HistoricalDataset
    strategy: SimulationStrategy
    instruments: Mapping[str, SolanaInstrument]
    starting_equity: Decimal
    schedule: FeeSchedule
    latency: LatencyModel
    participation: Decimal
    impact_cap: Decimal
    created_at: datetime
    run_id: str = ""


@dataclass
class _Pending:
    command: BrokerCommand
    fill_after: datetime
    expire_after: datetime
    mark_override: tuple[tuple[str, Decimal], ...]


@dataclass
class _Cash:
    sol: Decimal


class _Clock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment


def run_backtest(
    spec: BacktestSpec, *, mode: ExecutionMode = ExecutionMode.PAPER
) -> SimulationReport:
    """Run one strategy. Read-only mode refuses before any order is stored."""

    if mode is not ExecutionMode.PAPER:
        raise TradingDisabled("Read-only mode does not run a paper backtest.")
    if spec.starting_equity <= 0:
        raise TradingValidationError("Starting paper equity must be positive.")
    series = HistoricalSeries(spec.dataset)
    _require_instruments(series, spec.instruments)
    clock = _Clock(spec.created_at)
    store = MemoryTradingStore()
    gateway = PaperExecutionGateway(mode, store, clock)
    StrategyManager(mode, store, gateway, clock).register(
        spec.strategy.strategy_id,
        spec.strategy.name,
        dict(spec.strategy.parameter_pairs()),
    )
    StrategyManager(mode, store, gateway, clock).start(spec.strategy.strategy_id)
    broker = PaperBroker(
        mode,
        store,
        clock,
        spec.schedule,
        spec.latency,
        participation=spec.participation,
        impact_cap=spec.impact_cap,
    )
    state = _Run(
        clock,
        store,
        gateway,
        broker,
        _Cash(spec.starting_equity),
        [],
        [],
        [spec.starting_equity],
        0,
    )
    for moment in series.timestamps:
        clock.moment = moment
        _resolve_pending(spec, series, moment, state)
        for mint in series.mints():
            bar = series.bar_at(mint, moment)
            if bar is None:
                continue
            _exits(spec, series, mint, bar, moment, state)
            _entries(spec, series, mint, bar, moment, state)
        if any(item.quantity > 0 for item in store.list_positions()):
            state.in_market += 1
        equity, _marks = _value(state.cash.sol, store, series, moment, ())
        if equity is not None:
            state.curve.append(equity)
    for item in state.pending:
        state.refusals.append(
            Refusal(
                item.command.instrument.mint,
                item.fill_after,
                item.command.side.value,
                "no_observation_in_window",
            )
        )
    ending, _marks = _value(state.cash.sol, store, series, clock.moment, ())
    return _report(
        spec, store, series, tuple(state.curve), state.in_market, ending, tuple(state.refusals)
    )


@dataclass
class _Run:
    clock: _Clock
    store: MemoryTradingStore
    gateway: PaperExecutionGateway
    broker: PaperBroker
    cash: _Cash
    pending: list[_Pending]
    refusals: list[Refusal]
    curve: list[Decimal]
    in_market: int


def _exits(
    spec: BacktestSpec,
    series: HistoricalSeries,
    mint: str,
    bar: HistoricalBar,
    moment: datetime,
    state: _Run,
) -> None:
    equity, marks = _value(state.cash.sol, state.store, series, moment, ())
    command, refusal = state.broker.plan_exit(
        bar,
        spec.instruments[mint],
        equity_quote=equity,
        sol_balance=state.cash.sol,
        marks=marks,
        idempotency_key=_key("exit", len(state.store.orders) + len(state.pending)),
    )
    if refusal is not None and refusal.refusal is not None:
        state.refusals.append(Refusal(mint, moment, OrderSide.SELL.value, refusal.refusal))
    if command is None:
        return
    override = ((mint, bar.close),) if bar.close is not None else ()
    _schedule(spec, series, moment, command, override, state)


def _entries(
    spec: BacktestSpec,
    series: HistoricalSeries,
    mint: str,
    bar: HistoricalBar,
    moment: datetime,
    state: _Run,
) -> None:
    position = next((item for item in state.store.list_positions() if item.mint == mint), None)
    quantity = Decimal(0) if position is None else position.quantity
    view = StrategyView(
        mint=mint,
        decided_at=moment,
        bars=series.visible(mint, moment),
        signals=tuple(item for item in series.dataset.signals if item.observed_at <= moment),
        position_quantity=quantity,
    )
    intent = spec.strategy.on_bar(view)
    if intent is None:
        return
    if intent.side is OrderSide.SELL and quantity <= 0:
        return
    equity, marks = _value(state.cash.sol, state.store, series, moment, ())
    command = BrokerCommand(
        strategy_id=spec.strategy.strategy_id,
        instrument=spec.instruments[mint],
        side=intent.side,
        quantity=quantity if intent.side is OrderSide.SELL else probe_quantity(),
        bar=bar,
        exit_kind=intent.exit_kind,
        stop_fraction=intent.stop_fraction,
        signal_ref=intent.signal_ref,
        idempotency_key=_key(
            intent.side.value.lower(), len(state.store.orders) + len(state.pending)
        ),
        narrative=spec.strategy.narrative,
        equity_quote=equity,
        sol_balance=state.cash.sol,
        marks=marks,
    )
    override = (
        ((mint, bar.close),) if intent.side is OrderSide.SELL and bar.close is not None else ()
    )
    _schedule(spec, series, moment, command, override, state)


def _schedule(
    spec: BacktestSpec,
    series: HistoricalSeries,
    moment: datetime,
    command: BrokerCommand,
    override: tuple[tuple[str, Decimal], ...],
    state: _Run,
) -> None:
    start, end = fill_window(moment, spec.latency)
    if spec.latency.delay_seconds == 0:
        _fill(series, moment, command, command.bar, override, state)
        return
    state.pending.append(_Pending(command, start, end, override))


def _resolve_pending(
    spec: BacktestSpec, series: HistoricalSeries, moment: datetime, state: _Run
) -> None:
    del spec
    kept: list[_Pending] = []
    for item in state.pending:
        if moment < item.fill_after:
            kept.append(item)
            continue
        bar = series.bar_at(item.command.instrument.mint, moment)
        if bar is None:
            if moment > item.expire_after:
                state.refusals.append(
                    Refusal(
                        item.command.instrument.mint,
                        item.fill_after,
                        item.command.side.value,
                        "no_observation_in_window",
                    )
                )
            else:
                kept.append(item)
            continue
        if moment > item.expire_after:
            state.refusals.append(
                Refusal(
                    item.command.instrument.mint,
                    moment,
                    item.command.side.value,
                    "quote_unavailable_within_delay",
                )
            )
            continue
        _fill(series, moment, item.command, bar, item.mark_override, state)
    state.pending = kept


def _fill(
    series: HistoricalSeries,
    moment: datetime,
    command: BrokerCommand,
    bar: HistoricalBar,
    override: tuple[tuple[str, Decimal], ...],
    state: _Run,
) -> None:
    equity, marks = _value(state.cash.sol, state.store, series, moment, override)
    try:
        result = state.broker.execute(
            replace(command, bar=bar, equity_quote=equity, sol_balance=state.cash.sol, marks=marks)
        )
    except TradingValidationError:
        state.refusals.append(Refusal(bar.mint, moment, command.side.value, "validation_rejected"))
        return
    _collect(result, bar.mint, moment, command.side, state.refusals)
    if result.order is None:
        return
    _apply_cash(state.cash, result.order)
    if result.order.state is OrderState.CONFIRMED:
        state.gateway.reconcile(
            result.order.client_order_id,
            ExecutionReport(
                client_order_id=result.order.client_order_id,
                state=result.order.state,
                filled_quantity=result.order.filled_quantity,
                fill_price=result.order.fill_price,
            ),
        )


def _collect(
    result: BrokerResult, mint: str, moment: datetime, side: OrderSide, refusals: list[Refusal]
) -> None:
    if result.refusal is not None:
        refusals.append(Refusal(mint, moment, side.value, result.refusal))
        return
    order = result.order
    if order is not None and order.state is OrderState.FAILED:
        refusals.append(Refusal(mint, moment, side.value, order.reason or "denied"))


def _apply_cash(cash: _Cash, order: OrderRecord) -> None:
    if order.filled_quantity <= 0 or order.fill_price is None:
        return
    notional = order.fill_price * order.filled_quantity
    if order.side is OrderSide.BUY:
        cash.sol -= notional + order.fee_quote
    else:
        cash.sol += notional - order.fee_quote


def _value(
    sol: Decimal,
    store: MemoryTradingStore,
    series: HistoricalSeries,
    moment: datetime,
    override: tuple[tuple[str, Decimal], ...],
) -> tuple[Decimal | None, tuple[tuple[str, Decimal], ...]]:
    forced = dict(override)
    marks: list[tuple[str, Decimal]] = []
    deployed = Decimal(0)
    for position in store.list_positions():
        if position.quantity <= 0:
            continue
        mark = forced.get(position.mint, series.last_close(position.mint, moment))
        if mark is None or mark <= 0:
            return None, ()
        marks.append((position.mint, mark))
        deployed += position.quantity * mark
    return sol + deployed, tuple(marks)


def _report(
    spec: BacktestSpec,
    store: MemoryTradingStore,
    series: HistoricalSeries,
    curve: tuple[Decimal, ...],
    in_market: int,
    ending: Decimal | None,
    refusals: tuple[Refusal, ...],
) -> SimulationReport:
    orders = store.list_orders()
    performance = measure(
        orders=orders,
        campaigns=store.load_shield().campaigns,
        strategy_id=spec.strategy.strategy_id,
        starting_equity=spec.starting_equity,
        ending_equity=ending,
        equity_curve=curve,
        bars_in_market=in_market,
        bar_count=len(series.timestamps),
    )
    limitations = list(BASE_LIMITATIONS)
    limitations.extend(spec.dataset.limitations)
    limitations.append(spec.dataset.selection_note)
    limitations.extend(performance.limitations)
    if any(bar.volume_quote is not None and bar.base_volume is None for bar in spec.dataset.bars):
        limitations.append("candle_volume_was_not_used_as_base_size")
    if not spec.dataset.members:
        limitations.append("No universe was declared. Survivorship is not measured.")
    return SimulationReport(
        run_id=spec.run_id or f"run-{uuid.uuid4().hex[:12]}",
        dataset_id=spec.dataset.dataset_id,
        kind="backtest",
        strategy_id=spec.strategy.strategy_id,
        created_at=spec.created_at,
        starting_equity=spec.starting_equity,
        ending_equity=ending,
        performance=performance,
        orders=tuple(_order_summary(order) for order in orders),
        refusals=refusals,
        missing_tokens=missing_mints(spec.dataset),
        limitations=tuple(dict.fromkeys(limitations)),
        parameters_deployed=False,
        windows=(),
        strategies=(
            StrategySummary(
                spec.strategy.strategy_id,
                spec.strategy.name,
                performance.net_profit,
                performance.trade_count,
                performance.max_drawdown,
                spec.strategy.parameter_pairs(),
            ),
        ),
    )


def _order_summary(order: OrderRecord) -> OrderSummary:
    return OrderSummary(
        client_order_id=order.client_order_id,
        strategy_id=order.strategy_id,
        mint=order.mint,
        side=order.side.value,
        state=order.state.value,
        quantity=order.quantity,
        filled_quantity=order.filled_quantity,
        fill_price=order.fill_price,
        fee_quote=order.fee_quote,
        slippage_quote=order.slippage_quote,
        shield_decision=order.shield_decision,
        reason=order.reason,
    )


def _require_instruments(
    series: HistoricalSeries, instruments: Mapping[str, SolanaInstrument]
) -> None:
    for mint in series.mints():
        instrument = instruments.get(mint)
        if instrument is None or instrument.mint != mint or instrument.quote_symbol != "SOL":
            raise TradingValidationError("Every traded mint needs a SOL instrument definition.")


def _key(prefix: str, count: int) -> str:
    token = prefix.strip().lower() or "ord"
    return f"bt-{token}-{count:04d}"
