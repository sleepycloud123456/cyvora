"""Paper ledger routes. They do not call GMGN or a signer."""

from __future__ import annotations

from collections.abc import Callable
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
from domain.trading import (
    SHIELD_NOT_AUTHORIZED,
    OrderRecord,
    OrderSide,
    PositionRecord,
    SimulationOutcome,
    SolanaInstrument,
    StrategyRecord,
    TradingSnapshot,
)
from trading.execution.gateway import (
    PaperExecutionGateway,
    PaperOrderRequest,
    refuse_live_execution,
)
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
def trading_status(settings: SettingsDep) -> StatusModel:
    """Report the paper boundary. This route does not open a venue connection."""

    return StatusModel(
        execution_mode=settings.execution_mode.value,
        live_trading_enabled=False,
        paper_orders_enabled=settings.execution_mode is ExecutionMode.PAPER,
        shield_decision=SHIELD_NOT_AUTHORIZED,
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
