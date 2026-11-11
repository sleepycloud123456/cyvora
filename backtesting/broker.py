"""Paper broker. Every order is submitted through Shield. Nothing is signed."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from backtesting.costs import require_schedule
from backtesting.fills import price_order
from backtesting.latency import require_latency
from backtesting.numbers import quantize_down
from domain.enums import ExecutionMode
from domain.exceptions import TradingValidationError
from domain.shield import EmergencyEvidence, ExitKind, RiskIntent
from domain.simulation import (
    ExecutionAssumption,
    FeeSchedule,
    FillPlan,
    HistoricalBar,
    LatencyModel,
)
from domain.trading import (
    OrderRecord,
    OrderSide,
    PositionRecord,
    SimulationOutcome,
    SolanaInstrument,
)
from shield.engine import evaluate, record_trail
from trading.execution.gateway import PaperExecutionGateway, PaperOrderRequest
from trading.store import TradingStore
from trading.strategies.manager import StrategyManager

_SIZE_REASONS = frozenset(
    {
        "risk_per_trade",
        "max_deployed",
        "sol_reserve",
        "liquidity_participation",
        "price_impact",
        "correlation_cluster",
    }
)
_PROBE = Decimal("1000000000")


@dataclass(frozen=True)
class BrokerCommand:
    """One simulated intent. The caller cannot mark it approved."""

    strategy_id: str
    instrument: SolanaInstrument
    side: OrderSide
    quantity: Decimal
    bar: HistoricalBar
    exit_kind: str
    stop_fraction: Decimal | None
    signal_ref: str | None
    idempotency_key: str
    narrative: str
    equity_quote: Decimal | None
    sol_balance: Decimal | None
    marks: tuple[tuple[str, Decimal], ...]
    emergency: EmergencyEvidence | None = None


@dataclass(frozen=True)
class BrokerResult:
    """The stored paper order, or a refusal that did not invent a fill."""

    order: OrderRecord | None
    assumption: ExecutionAssumption | None
    refusal: str | None
    limitations: tuple[str, ...]


class PaperBroker:
    """Price an order with the cost models, then hand it to the paper gateway."""

    def __init__(
        self,
        mode: ExecutionMode,
        store: TradingStore,
        clock: Callable[[], datetime],
        schedule: FeeSchedule,
        latency: LatencyModel,
        *,
        participation: Decimal,
        impact_cap: Decimal,
        entries_blocked: Callable[[], bool] | None = None,
    ) -> None:
        self._mode = mode
        self._store = store
        self._clock = clock
        self._schedule = require_schedule(schedule)
        self._latency = require_latency(latency)
        if participation <= 0 or participation > 1 or impact_cap <= 0 or impact_cap >= 1:
            raise TradingValidationError("Participation and impact cap must be between 0 and 1.")
        self._participation = participation
        self._impact_cap = impact_cap
        gateway = PaperExecutionGateway(mode, store, clock, entries_blocked=entries_blocked)
        self._manager = StrategyManager(mode, store, gateway, clock)

    def execute(self, command: BrokerCommand) -> BrokerResult:
        """Submit one priced order. An unpriced bar is refused before the ledger write."""

        plan = self._price(command, command.quantity)
        if not plan.priced or plan.quantity is None:
            return BrokerResult(None, None, plan.reason or "unpriced", plan.limitations)
        plan = self._fit_risk(command, plan)
        if (
            not plan.priced
            or plan.quantity is None
            or plan.reference_price is None
            or plan.slippage_quote is None
            or plan.fee_quote is None
        ):
            return BrokerResult(None, None, plan.reason or "unpriced", plan.limitations)
        order = self._manager.submit(command.strategy_id, self._request(command, plan))
        assumption = ExecutionAssumption(
            client_order_id=order.client_order_id,
            model=plan.model or "unpriced",
            impact=plan.impact,
            fee_quote=order.fee_quote,
            slippage_quote=order.slippage_quote,
            delay_seconds=self._latency.delay_seconds,
            limitations=plan.limitations,
            simulated=True,
            live_trading_enabled=False,
        )
        return BrokerResult(order, assumption, None, plan.limitations)

    def plan_exit(
        self,
        bar: HistoricalBar,
        instrument: SolanaInstrument,
        *,
        equity_quote: Decimal | None,
        sol_balance: Decimal | None,
        marks: tuple[tuple[str, Decimal], ...],
        idempotency_key: str,
    ) -> tuple[BrokerCommand | None, BrokerResult | None]:
        """Choose a due exit without filling it. The trail update is stored now."""

        position = _position(self._store.list_positions(), bar.mint)
        if position is None or position.quantity <= 0:
            return None, None
        snapshot = self._store.load_shield()
        plan = next((item for item in snapshot.stops if item.mint == bar.mint), None)
        if plan is None or bar.close is None or bar.close <= 0:
            return None, BrokerResult(
                None, None, "mark_missing", ("candle_close_is_a_mark_not_a_fill",)
            )
        campaign = next(
            (
                item
                for item in snapshot.campaigns
                if item.mint == bar.mint and item.closed_at is None
            ),
            None,
        )
        if campaign is None:
            return None, BrokerResult(None, None, "campaign_missing", ())
        if bar.close <= plan.stop_price:
            return (
                self._command(
                    bar,
                    instrument,
                    campaign.strategy_id,
                    position.quantity,
                    ExitKind.NORMAL.value,
                    equity_quote,
                    sol_balance,
                    marks,
                    f"{idempotency_key}-stop",
                ),
                None,
            )
        updated, _status = record_trail(snapshot, bar.mint, bar.close, None, self._clock())
        self._store.save_shield(updated)
        plan = next(item for item in updated.stops if item.mint == bar.mint)
        for level in plan.levels:
            target = plan.entry_price * (Decimal(1) + level.gain_fraction)
            left = level.planned_quantity - level.consumed_quantity
            if bar.close >= target and left > 0:
                return (
                    self._command(
                        bar,
                        instrument,
                        campaign.strategy_id,
                        min(position.quantity, left),
                        ExitKind.TAKE_PROFIT.value,
                        equity_quote,
                        sol_balance,
                        marks,
                        f"{idempotency_key}-tp",
                    ),
                    None,
                )
        elapsed = self._clock() - campaign.opened_at
        if elapsed >= timedelta(seconds=updated.limits.time_exit_seconds):
            return (
                self._command(
                    bar,
                    instrument,
                    campaign.strategy_id,
                    position.quantity,
                    ExitKind.TIME.value,
                    equity_quote,
                    sol_balance,
                    marks,
                    f"{idempotency_key}-time",
                ),
                None,
            )
        return None, None

    def maintain(
        self,
        bar: HistoricalBar,
        instrument: SolanaInstrument,
        *,
        equity_quote: Decimal | None,
        sol_balance: Decimal | None,
        marks: tuple[tuple[str, Decimal], ...],
        idempotency_key: str,
    ) -> tuple[BrokerResult, ...]:
        """Submit a due exit immediately. Shield still approves or denies it."""

        command, refusal = self.plan_exit(
            bar,
            instrument,
            equity_quote=equity_quote,
            sol_balance=sol_balance,
            marks=marks,
            idempotency_key=idempotency_key,
        )
        if refusal is not None:
            return (refusal,)
        if command is None:
            return ()
        return (self.execute(command),)

    def _command(
        self,
        bar: HistoricalBar,
        instrument: SolanaInstrument,
        strategy_id: str,
        quantity: Decimal,
        kind: str,
        equity_quote: Decimal | None,
        sol_balance: Decimal | None,
        marks: tuple[tuple[str, Decimal], ...],
        key: str,
    ) -> BrokerCommand:
        return BrokerCommand(
            strategy_id=strategy_id,
            instrument=instrument,
            side=OrderSide.SELL,
            quantity=quantity,
            bar=bar,
            exit_kind=kind,
            stop_fraction=None,
            signal_ref=None,
            idempotency_key=key,
            narrative="exit",
            equity_quote=equity_quote,
            sol_balance=sol_balance,
            marks=marks,
        )

    def _price(self, command: BrokerCommand, quantity: Decimal) -> FillPlan:
        return price_order(
            command.bar,
            command.side,
            quantity,
            command.instrument,
            self._schedule,
            participation=self._participation,
            impact_cap=self._impact_cap,
        )

    def _fit_risk(self, command: BrokerCommand, plan: FillPlan) -> FillPlan:
        if command.side is not OrderSide.BUY:
            return plan
        for _attempt in range(3):
            if not plan.priced or plan.quantity is None:
                return plan
            decision = evaluate(
                self._store.load_shield(),
                self._intent(command, plan),
                self._store.list_positions(),
                self._store.list_orders(),
                self._clock(),
            )
            allowed = decision.allowed_quantity
            if decision.approved or decision.reason not in _SIZE_REASONS or allowed is None:
                return plan
            if allowed <= 0 or plan.quantity <= allowed:
                return plan
            plan = self._price(command, allowed)
        return plan

    def _request(self, command: BrokerCommand, plan: FillPlan) -> PaperOrderRequest:
        if (
            plan.quantity is None
            or plan.reference_price is None
            or plan.slippage_quote is None
            or plan.fee_quote is None
            or plan.outcome is None
        ):
            raise TradingValidationError("An unpriced plan cannot be submitted.")
        return PaperOrderRequest(
            strategy_id=command.strategy_id,
            instrument=command.instrument,
            side=command.side,
            quantity=plan.quantity,
            reference_price=plan.reference_price,
            outcome=SimulationOutcome(plan.outcome),
            idempotency_key=command.idempotency_key,
            fee_quote=plan.fee_quote,
            slippage_quote=plan.slippage_quote,
            shield_approved=False,
            risk=self._intent(command, plan),
        )

    def _intent(self, command: BrokerCommand, plan: FillPlan) -> RiskIntent:
        if (
            plan.quantity is None
            or plan.reference_price is None
            or plan.slippage_quote is None
            or plan.fee_quote is None
        ):
            raise TradingValidationError("An unpriced plan cannot be submitted.")
        if command.side is OrderSide.BUY:
            execution = plan.reference_price + plan.slippage_quote
        else:
            execution = plan.reference_price - plan.slippage_quote
        stop = None
        if command.side is OrderSide.BUY and command.stop_fraction is not None:
            stop = quantize_down(
                execution * (Decimal(1) - command.stop_fraction),
                command.instrument.price_decimals,
            )
        return RiskIntent(
            mint=command.instrument.mint,
            side=command.side.value,
            quantity=plan.quantity,
            reference_price=plan.reference_price,
            fee_quote=plan.fee_quote,
            slippage_quote=plan.slippage_quote,
            size_decimals=command.instrument.size_decimals,
            price_decimals=command.instrument.price_decimals,
            quote_decimals=command.instrument.quote_decimals,
            quote_symbol=command.instrument.quote_symbol,
            stop_price=stop,
            equity_quote=command.equity_quote,
            sol_balance=command.sol_balance,
            valued_at=self._clock() if command.equity_quote is not None else None,
            marks=command.marks,
            liquidity_quote=plan.liquidity_quote,
            volatility=command.bar.volatility,
            confidence=None,
            token_age_seconds=command.bar.token_age_seconds,
            market_condition=command.bar.market_condition,
            security=command.bar.security,
            creator=command.bar.creator,
            narrative=command.narrative,
            liquidity_provider=None,
            driver=None,
            estimated_impact=plan.impact,
            exit_kind=command.exit_kind,
            signal_ref=command.signal_ref,
            emergency=command.emergency,
        )


def probe_quantity() -> Decimal:
    """A request large enough for the liquidity model to apply its own cap."""

    return _PROBE


def _position(positions: tuple[PositionRecord, ...], mint: str) -> PositionRecord | None:
    return next((item for item in positions if item.mint == mint), None)
