"""Paper ledger routes. They do not call GMGN or a signer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.api.auth import require_local_token
from apps.api.dependencies import get_app_settings
from config.settings import Settings
from database.repositories.trading import PostgresTradingRepository
from domain.enums import ExecutionMode
from domain.exceptions import (
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    TradingDisabled,
    TradingValidationError,
)
from domain.shield import (
    EmergencyEvidence,
    ExitKind,
    RiskIntent,
    ShieldLimits,
    ShieldSnapshot,
    TakeProfitLevel,
)
from domain.trading import (
    OrderRecord,
    OrderSide,
    PositionRecord,
    SimulationOutcome,
    SolanaInstrument,
    StrategyRecord,
    TradingSnapshot,
)
from shield.engine import record_emergency, record_trail, recover, replace_limits
from shield.limits import validate_limits
from trading.execution.gateway import (
    PaperExecutionGateway,
    PaperOrderRequest,
    refuse_live_execution,
)
from trading.instruments import require_mint
from trading.store import TradingStore
from trading.strategies.manager import StrategyManager

router = APIRouter(dependencies=[Depends(require_local_token)], tags=["trading"])
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


class StatusModel(BaseModel):
    execution_mode: str
    live_trading_enabled: bool
    paper_orders_enabled: bool
    shield_decision: str
    nautilus_version: str
    simulated: bool


class StrategyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    name: str
    parameters: dict[str, str] = Field(default_factory=dict)


class StrategyModel(BaseModel):
    strategy_id: str
    name: str
    state: str
    parameters: dict[str, str]


class OrderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    mint: str
    symbol: str
    side: OrderSide
    quantity: str
    reference_price: str
    quote_symbol: str
    size_decimals: int
    price_decimals: int
    quote_decimals: int
    outcome: SimulationOutcome = SimulationOutcome.FILL
    idempotency_key: str
    fill_quantity: str | None = None
    fee_quote: str = "0"
    slippage_quote: str = "0"
    shield_approved: bool = False
    stop_price: str | None = None
    equity_quote: str | None = None
    sol_balance: str | None = None
    valued_at: str | None = None
    liquidity_quote: str | None = None
    volatility: str | None = None
    confidence: str | None = None
    token_age_seconds: int | None = None
    market_condition: str | None = None
    security: str | None = None
    creator: str | None = None
    narrative: str | None = None
    liquidity_provider: str | None = None
    driver: str | None = None
    estimated_impact: str | None = None
    exit_kind: str | None = None
    signal_ref: str | None = None
    marks: list[MarkBody] = Field(default_factory=list)
    emergency: EmergencyBody | None = None


class MarkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mint: str
    price: str


class EmergencyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous_liquidity: str | None = None
    current_liquidity: str | None = None
    previous_price: str | None = None
    current_price: str | None = None
    whale_sell_reported: bool = False
    whale_source: str | None = None
    smart_money_exit_reported: bool = False
    smart_money_source: str | None = None
    estimated_impact: str | None = None
    trading_restricted: bool = False
    restriction_source: str | None = None
    quote_observed_at: str | None = None


class LevelBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gain_fraction: str
    quantity_fraction: str


class LimitsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_deployed_fraction: str
    min_sol_reserve_fraction: str
    risk_per_trade_fraction: str
    daily_loss_fraction: str
    max_drawdown_fraction: str
    max_consecutive_losses: int
    max_liquidity_participation: str
    max_cluster_fraction: str
    max_price_impact: str
    volatility_multiplier: str
    liquidity_widen_below: str
    young_token_seconds: int
    young_token_multiplier: str
    stressed_multiplier: str
    trail_distance_fraction: str
    trail_activation_fraction: str
    break_even_fraction: str
    trail_min_interval_seconds: int
    liquidity_removal_ratio: str
    price_collapse_ratio: str
    max_quote_age_seconds: int
    max_valuation_age_seconds: int
    time_exit_seconds: int
    take_profit_levels: list[LevelBody]


class RecoveryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phrase: str
    equity_quote: str
    sol_balance: str
    valued_at: str
    marks: list[MarkBody] = Field(default_factory=list)
    reset_loss_streak: bool = False
    emergency: EmergencyBody | None = None


class TrailBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mint: str
    mark: str
    volatility: str | None = None


class ShieldModel(BaseModel):
    posture: str
    live_trading_enabled: bool
    high_water_equity: str | None
    consecutive_losses: int
    breach_latched: bool
    breach_reasons: list[str]
    halt_entries: bool
    daily_session: str | None
    equity_at_open: str | None
    last_equity: str | None
    notices: list[str]
    limits: dict[str, str]


class OrderModel(BaseModel):
    client_order_id: str
    idempotency_key: str
    strategy_id: str
    mint: str
    symbol: str
    side: str
    state: str
    quantity: str
    filled_quantity: str
    reference_price: str
    fill_price: str | None
    fee_quote: str
    slippage_quote: str
    quote_symbol: str
    outcome: str
    shield_decision: str
    simulated: bool
    reason: str | None


class PositionModel(BaseModel):
    mint: str
    quantity: str
    average_price: str | None
    cost_quote: str
    realized_pnl_quote: str
    quote_symbol: str


class ReportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str | None = None
    filled_quantity: str | None = None
    fill_price: str | None = None
    missing: bool = False


class ReconciliationModel(BaseModel):
    client_order_id: str
    status: str
    detail: str


def _store(request: Request, settings: Settings) -> TradingStore:
    injected = getattr(request.app.state, "trading_store", None)
    if injected is not None:
        return injected
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    return PostgresTradingRepository(settings)


def _clock(request: Request) -> Callable[[], datetime]:
    injected = getattr(request.app.state, "trading_clock", None)
    if injected is not None:
        return injected
    return lambda: datetime.now(UTC)


def _services(
    request: Request, settings: Settings
) -> tuple[StrategyManager, PaperExecutionGateway]:
    store = _store(request, settings)
    clock = _clock(request)
    gateway = PaperExecutionGateway(settings.execution_mode, store, clock)
    return StrategyManager(settings.execution_mode, store, gateway, clock), gateway


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise HTTPException(status_code=422, detail="A decimal field is invalid.") from exc
    if not parsed.is_finite():
        raise HTTPException(status_code=422, detail="A decimal field is invalid.")
    return parsed


def _order_model(order: OrderRecord) -> OrderModel:
    return OrderModel(
        client_order_id=order.client_order_id,
        idempotency_key=order.idempotency_key,
        strategy_id=order.strategy_id,
        mint=order.mint,
        symbol=order.symbol,
        side=order.side.value,
        state=order.state.value,
        quantity=str(order.quantity),
        filled_quantity=str(order.filled_quantity),
        reference_price=str(order.reference_price),
        fill_price=None if order.fill_price is None else str(order.fill_price),
        fee_quote=str(order.fee_quote),
        slippage_quote=str(order.slippage_quote),
        quote_symbol=order.quote_symbol,
        outcome=order.outcome.value,
        shield_decision=order.shield_decision,
        simulated=order.simulated,
        reason=order.reason,
    )


def _position_model(position: PositionRecord) -> PositionModel:
    return PositionModel(
        mint=position.mint,
        quantity=str(position.quantity),
        average_price=None if position.average_price is None else str(position.average_price),
        cost_quote=str(position.cost_quote),
        realized_pnl_quote=str(position.realized_pnl_quote),
        quote_symbol=position.quote_symbol,
    )


def _strategy_model(strategy: StrategyRecord) -> StrategyModel:
    return StrategyModel(
        strategy_id=strategy.strategy_id,
        name=strategy.name,
        state=strategy.state.value,
        parameters=dict(strategy.parameters),
    )


def _call(action: Callable[[], object]) -> object:
    try:
        return action()
    except TradingDisabled as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TradingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (DatabaseNotConfiguredError, DatabaseUnavailableError) as exc:
        raise HTTPException(
            status_code=503, detail="Stored simulation records are unavailable."
        ) from exc


@router.get("/trading/status", response_model=StatusModel)
def trading_status(request: Request, settings: SettingsDep) -> StatusModel:
    """Report the paper boundary. This route does not open a venue connection."""

    posture = "enforcing"
    store = getattr(request.app.state, "trading_store", None)
    if store is not None:
        posture = _posture(store.load_shield())
    elif settings.database_url:
        loaded = _call(lambda: _store(request, settings).load_shield())
        if isinstance(loaded, ShieldSnapshot):
            posture = _posture(loaded)
    return StatusModel(
        execution_mode=settings.execution_mode.value,
        live_trading_enabled=False,
        paper_orders_enabled=settings.execution_mode is ExecutionMode.PAPER,
        shield_decision=posture,
        nautilus_version=version("nautilus-trader"),
        simulated=True,
    )


@router.post("/trading/live/{operation}")
def reject_live(operation: str) -> None:
    """Refuse a live operation before any store or network call."""

    try:
        refuse_live_execution(operation)
    except TradingDisabled as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/trading/orders", response_model=list[OrderModel])
def list_orders(request: Request, settings: SettingsDep) -> list[OrderModel]:
    snapshot = _call(lambda: _store(request, settings).snapshot())
    if not isinstance(snapshot, TradingSnapshot):
        return []
    return [_order_model(order) for order in snapshot.orders]


@router.get("/trading/positions", response_model=list[PositionModel])
def list_positions(request: Request, settings: SettingsDep) -> list[PositionModel]:
    snapshot = _call(lambda: _store(request, settings).snapshot())
    if not isinstance(snapshot, TradingSnapshot):
        return []
    return [_position_model(position) for position in snapshot.positions]


@router.get("/trading/strategies", response_model=list[StrategyModel])
def list_strategies(request: Request, settings: SettingsDep) -> list[StrategyModel]:
    snapshot = _call(lambda: _store(request, settings).snapshot())
    if not isinstance(snapshot, TradingSnapshot):
        return []
    return [_strategy_model(strategy) for strategy in snapshot.strategies]


@router.post("/trading/strategies", response_model=StrategyModel)
def register_strategy(body: StrategyBody, request: Request, settings: SettingsDep) -> StrategyModel:
    manager, _gateway = _services(request, settings)
    record = _call(lambda: manager.register(body.strategy_id, body.name, body.parameters))
    if not isinstance(record, StrategyRecord):
        raise HTTPException(status_code=500, detail="Internal server error")
    return _strategy_model(record)


@router.post("/trading/strategies/{strategy_id}/start", response_model=StrategyModel)
def start_strategy(strategy_id: str, request: Request, settings: SettingsDep) -> StrategyModel:
    manager, _gateway = _services(request, settings)
    record = _call(lambda: manager.start(strategy_id))
    if not isinstance(record, StrategyRecord):
        raise HTTPException(status_code=500, detail="Internal server error")
    return _strategy_model(record)


@router.post("/trading/strategies/{strategy_id}/stop", response_model=StrategyModel)
def stop_strategy(strategy_id: str, request: Request, settings: SettingsDep) -> StrategyModel:
    manager, _gateway = _services(request, settings)
    record = _call(lambda: manager.stop(strategy_id))
    if not isinstance(record, StrategyRecord):
        raise HTTPException(status_code=500, detail="Internal server error")
    return _strategy_model(record)


@router.post("/trading/paper/orders", response_model=OrderModel)
def submit_paper_order(body: OrderBody, request: Request, settings: SettingsDep) -> OrderModel:
    """Store one explicit paper order. The price is the caller's reference price."""

    manager, _gateway = _services(request, settings)
    request_order = PaperOrderRequest(
        strategy_id=body.strategy_id,
        instrument=SolanaInstrument(
            mint=body.mint,
            symbol=body.symbol,
            size_decimals=body.size_decimals,
            price_decimals=body.price_decimals,
            quote_symbol=body.quote_symbol,
            quote_decimals=body.quote_decimals,
        ),
        side=body.side,
        quantity=_decimal(body.quantity),
        reference_price=_decimal(body.reference_price),
        outcome=body.outcome,
        idempotency_key=body.idempotency_key,
        fill_quantity=None if body.fill_quantity is None else _decimal(body.fill_quantity),
        fee_quote=_decimal(body.fee_quote),
        slippage_quote=_decimal(body.slippage_quote),
        shield_approved=body.shield_approved,
        risk=_risk_intent(body),
    )
    order = _call(lambda: manager.submit(body.strategy_id, request_order))
    if not isinstance(order, OrderRecord):
        raise HTTPException(status_code=500, detail="Internal server error")
    return _order_model(order)


@router.post("/trading/orders/{client_order_id}/reconcile", response_model=ReconciliationModel)
def reconcile_order(
    client_order_id: str,
    body: ReportBody,
    request: Request,
    settings: SettingsDep,
) -> ReconciliationModel:
    """Compare a stored order with a supplied report. A mismatch does not retry."""

    from domain.trading import ExecutionReport, OrderState

    _manager, gateway = _services(request, settings)
    report = None
    if not body.missing:
        if body.state is None or body.filled_quantity is None:
            raise HTTPException(
                status_code=422, detail="A report needs a state and a filled quantity."
            )
        try:
            state = OrderState(body.state)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Unknown order state.") from exc
        report = ExecutionReport(
            client_order_id=client_order_id,
            state=state,
            filled_quantity=_decimal(body.filled_quantity),
            fill_price=None if body.fill_price is None else _decimal(body.fill_price),
        )
    record = _call(lambda: gateway.reconcile(client_order_id, report))
    from domain.trading import ReconciliationRecord

    if not isinstance(record, ReconciliationRecord):
        raise HTTPException(status_code=500, detail="Internal server error")
    return ReconciliationModel(
        client_order_id=record.client_order_id,
        status=record.status.value,
        detail=record.detail,
    )


@router.get("/trading/shield", response_model=ShieldModel)
def read_shield(request: Request, settings: SettingsDep) -> ShieldModel:
    """Return the stored paper risk book. An empty book is the documented defaults."""

    store = _store(request, settings)
    snapshot = _call(store.load_shield)
    notices = _call(store.list_notices)
    if not isinstance(snapshot, ShieldSnapshot) or not isinstance(notices, tuple):
        raise HTTPException(status_code=500, detail="Internal server error")
    return _shield_model(snapshot, notices)


@router.put("/trading/shield/limits", response_model=ShieldModel)
def update_limits(body: LimitsBody, request: Request, settings: SettingsDep) -> ShieldModel:
    """Replace Shield limits. A breach and the high-water mark stay as they are."""

    store = _store(request, settings)
    current = _call(store.load_shield)
    if not isinstance(current, ShieldSnapshot):
        raise HTTPException(status_code=500, detail="Internal server error")
    updated = _call(lambda: replace_limits(current, _limits(body)))
    if not isinstance(updated, ShieldSnapshot):
        raise HTTPException(status_code=500, detail="Internal server error")
    _call(lambda: store.save_shield(updated))
    return _shield_model(updated, store.list_notices())


@router.post("/trading/shield/recover", response_model=ShieldModel)
def recover_entries(body: RecoveryBody, request: Request, settings: SettingsDep) -> ShieldModel:
    """Clear a latched breach only when the supplied valuation is back inside the limits."""

    store = _store(request, settings)
    current = _call(store.load_shield)
    if not isinstance(current, ShieldSnapshot):
        raise HTTPException(status_code=500, detail="Internal server error")
    positions = store.list_positions()
    intent = replace(
        _valuation_intent(body.equity_quote, body.sol_balance, body.valued_at, body.marks),
        emergency=None if body.emergency is None else _emergency(body.emergency),
    )
    result = _call(
        lambda: recover(
            current,
            body.phrase,
            intent,
            positions,
            _clock(request)(),
            reset_loss_streak=body.reset_loss_streak,
        )
    )
    if not isinstance(result, tuple) or len(result) != 3:
        raise HTTPException(status_code=500, detail="Internal server error")
    snapshot, problem, notices = result
    if not isinstance(snapshot, ShieldSnapshot) or not isinstance(notices, tuple):
        raise HTTPException(status_code=500, detail="Internal server error")
    if problem is not None:
        _call(lambda: store.save_shield(snapshot))
        raise HTTPException(status_code=422, detail=str(problem))
    _call(lambda: store.save_shield(snapshot, notices=notices))
    return _shield_model(snapshot, store.list_notices())


@router.post("/trading/shield/emergency/{mint}", response_model=ShieldModel)
def assess_emergency_route(
    mint: str, body: EmergencyBody, request: Request, settings: SettingsDep
) -> ShieldModel:
    """Record emergency triggers. This route does not submit an order."""

    store = _store(request, settings)
    current = _call(store.load_shield)
    if not isinstance(current, ShieldSnapshot):
        raise HTTPException(status_code=500, detail="Internal server error")
    checked = _call(lambda: require_mint(mint))
    if not isinstance(checked, str):
        raise HTTPException(status_code=500, detail="Internal server error")
    result = _call(lambda: record_emergency(current, checked, _emergency(body), _clock(request)()))
    if not isinstance(result, tuple):
        raise HTTPException(status_code=500, detail="Internal server error")
    snapshot, _triggers, notices = result
    if not isinstance(snapshot, ShieldSnapshot) or not isinstance(notices, tuple):
        raise HTTPException(status_code=500, detail="Internal server error")
    _call(lambda: store.save_shield(snapshot, notices=notices))
    return _shield_model(snapshot, store.list_notices())


@router.post("/trading/shield/trailing", response_model=ShieldModel)
def trail_stop(body: TrailBody, request: Request, settings: SettingsDep) -> ShieldModel:
    """Move one stored paper stop. The stop is not sent to a venue."""

    store = _store(request, settings)
    current = _call(store.load_shield)
    if not isinstance(current, ShieldSnapshot):
        raise HTTPException(status_code=500, detail="Internal server error")
    volatility = None if body.volatility is None else _decimal(body.volatility)
    result = _call(
        lambda: record_trail(current, body.mint, _decimal(body.mark), volatility, _clock(request)())
    )
    if not isinstance(result, tuple):
        raise HTTPException(status_code=500, detail="Internal server error")
    snapshot, _status = result
    if not isinstance(snapshot, ShieldSnapshot):
        raise HTTPException(status_code=500, detail="Internal server error")
    _call(lambda: store.save_shield(snapshot))
    return _shield_model(snapshot, store.list_notices())


def _posture(snapshot: ShieldSnapshot) -> str:
    if snapshot.breach_latched or snapshot.halt_entries:
        return "breached"
    return "enforcing"


def _shield_model(snapshot: ShieldSnapshot, notices: tuple[object, ...]) -> ShieldModel:
    daily = snapshot.daily[-1] if snapshot.daily else None
    limits = snapshot.limits
    lines = [getattr(notice, "detail", "") for notice in notices]
    return ShieldModel(
        posture=_posture(snapshot),
        live_trading_enabled=False,
        high_water_equity=None
        if snapshot.high_water_equity is None
        else str(snapshot.high_water_equity),
        consecutive_losses=snapshot.consecutive_losses,
        breach_latched=snapshot.breach_latched,
        breach_reasons=list(snapshot.breach_reasons),
        halt_entries=snapshot.halt_entries,
        daily_session=None if daily is None else daily.session_date.isoformat(),
        equity_at_open=None if daily is None else str(daily.equity_at_open),
        last_equity=None if daily is None else str(daily.last_equity),
        notices=[line for line in lines if line],
        limits={
            "max_deployed_fraction": str(limits.max_deployed_fraction),
            "min_sol_reserve_fraction": str(limits.min_sol_reserve_fraction),
            "risk_per_trade_fraction": str(limits.risk_per_trade_fraction),
            "daily_loss_fraction": str(limits.daily_loss_fraction),
            "max_drawdown_fraction": str(limits.max_drawdown_fraction),
            "max_consecutive_losses": str(limits.max_consecutive_losses),
        },
    )


def _risk_intent(body: OrderBody) -> RiskIntent:
    kind = body.exit_kind
    if kind is None:
        kind = ExitKind.ENTRY.value if body.side is OrderSide.BUY else ExitKind.NORMAL.value
    return RiskIntent(
        mint=body.mint,
        side=body.side.value,
        quantity=_decimal(body.quantity),
        reference_price=_decimal(body.reference_price),
        fee_quote=_decimal(body.fee_quote),
        slippage_quote=_decimal(body.slippage_quote),
        size_decimals=body.size_decimals,
        price_decimals=body.price_decimals,
        quote_decimals=body.quote_decimals,
        quote_symbol=body.quote_symbol,
        stop_price=None if body.stop_price is None else _decimal(body.stop_price),
        equity_quote=None if body.equity_quote is None else _decimal(body.equity_quote),
        sol_balance=None if body.sol_balance is None else _decimal(body.sol_balance),
        valued_at=None if body.valued_at is None else _instant(body.valued_at),
        marks=tuple((mark.mint, _decimal(mark.price)) for mark in body.marks),
        liquidity_quote=None if body.liquidity_quote is None else _decimal(body.liquidity_quote),
        volatility=None if body.volatility is None else _decimal(body.volatility),
        confidence=None if body.confidence is None else _decimal(body.confidence),
        token_age_seconds=body.token_age_seconds,
        market_condition=body.market_condition,
        security=body.security,
        creator=body.creator,
        narrative=body.narrative,
        liquidity_provider=body.liquidity_provider,
        driver=body.driver,
        estimated_impact=None if body.estimated_impact is None else _decimal(body.estimated_impact),
        exit_kind=kind,
        signal_ref=body.signal_ref,
        emergency=None if body.emergency is None else _emergency(body.emergency),
    )


def _valuation_intent(
    equity: str,
    sol_balance: str,
    valued_at: str,
    marks: list[MarkBody],
) -> RiskIntent:
    return RiskIntent(
        mint="So11111111111111111111111111111111111111112",
        side=OrderSide.BUY.value,
        quantity=Decimal(1),
        reference_price=Decimal(1),
        fee_quote=Decimal(0),
        slippage_quote=Decimal(0),
        size_decimals=6,
        price_decimals=6,
        quote_decimals=9,
        quote_symbol="SOL",
        stop_price=None,
        equity_quote=_decimal(equity),
        sol_balance=_decimal(sol_balance),
        valued_at=_instant(valued_at),
        marks=tuple((mark.mint, _decimal(mark.price)) for mark in marks),
        liquidity_quote=None,
        volatility=None,
        confidence=None,
        token_age_seconds=None,
        market_condition=None,
        security=None,
        creator=None,
        narrative=None,
        liquidity_provider=None,
        driver=None,
        estimated_impact=None,
        exit_kind=ExitKind.ENTRY.value,
        signal_ref=None,
        emergency=None,
    )


def _limits(body: LimitsBody) -> ShieldLimits:
    return validate_limits(
        ShieldLimits(
            max_deployed_fraction=_decimal(body.max_deployed_fraction),
            min_sol_reserve_fraction=_decimal(body.min_sol_reserve_fraction),
            risk_per_trade_fraction=_decimal(body.risk_per_trade_fraction),
            daily_loss_fraction=_decimal(body.daily_loss_fraction),
            max_drawdown_fraction=_decimal(body.max_drawdown_fraction),
            max_consecutive_losses=body.max_consecutive_losses,
            max_liquidity_participation=_decimal(body.max_liquidity_participation),
            max_cluster_fraction=_decimal(body.max_cluster_fraction),
            max_price_impact=_decimal(body.max_price_impact),
            volatility_multiplier=_decimal(body.volatility_multiplier),
            liquidity_widen_below=_decimal(body.liquidity_widen_below),
            young_token_seconds=body.young_token_seconds,
            young_token_multiplier=_decimal(body.young_token_multiplier),
            stressed_multiplier=_decimal(body.stressed_multiplier),
            trail_distance_fraction=_decimal(body.trail_distance_fraction),
            trail_activation_fraction=_decimal(body.trail_activation_fraction),
            break_even_fraction=_decimal(body.break_even_fraction),
            trail_min_interval_seconds=body.trail_min_interval_seconds,
            liquidity_removal_ratio=_decimal(body.liquidity_removal_ratio),
            price_collapse_ratio=_decimal(body.price_collapse_ratio),
            max_quote_age_seconds=body.max_quote_age_seconds,
            max_valuation_age_seconds=body.max_valuation_age_seconds,
            time_exit_seconds=body.time_exit_seconds,
            take_profit_levels=tuple(
                TakeProfitLevel(_decimal(level.gain_fraction), _decimal(level.quantity_fraction))
                for level in body.take_profit_levels
            ),
        )
    )


def _emergency(body: EmergencyBody) -> EmergencyEvidence:
    return EmergencyEvidence(
        previous_liquidity=_optional_decimal(body.previous_liquidity),
        current_liquidity=_optional_decimal(body.current_liquidity),
        previous_price=_optional_decimal(body.previous_price),
        current_price=_optional_decimal(body.current_price),
        whale_sell_reported=body.whale_sell_reported,
        whale_source=body.whale_source,
        smart_money_exit_reported=body.smart_money_exit_reported,
        smart_money_source=body.smart_money_source,
        estimated_impact=_optional_decimal(body.estimated_impact),
        trading_restricted=body.trading_restricted,
        restriction_source=body.restriction_source,
        quote_observed_at=None
        if body.quote_observed_at is None
        else _instant(body.quote_observed_at),
    )


def _optional_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value)


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="A timestamp must be ISO-8601.") from exc
    if parsed.tzinfo is None:
        raise HTTPException(status_code=422, detail="A timestamp must include a timezone.")
    return parsed
