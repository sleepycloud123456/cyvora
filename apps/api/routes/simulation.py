"""Simulation routes. They price paper orders and do not submit a transaction."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.api.auth import require_local_token
from apps.api.dependencies import get_app_settings
from apps.api.routes.trading import _clock, _store
from backtesting.broker import BrokerCommand, PaperBroker
from backtesting.compare import compare_strategies
from backtesting.engine import BacktestSpec, run_backtest
from backtesting.memory_store import MemorySimulationStore
from backtesting.reports import dump_report
from backtesting.strategies import strategy_by_name
from backtesting.walkforward import walk_forward
from config.settings import Settings
from database.repositories.simulation import PostgresSimulationRepository
from domain.enums import ExecutionMode
from domain.exceptions import (
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    TradingDisabled,
    TradingValidationError,
)
from domain.shield import ExitKind
from domain.simulation import (
    FeeSchedule,
    HistoricalBar,
    HistoricalDataset,
    HistoricalSignal,
    LatencyModel,
    UniverseMember,
)
from domain.trading import OrderSide, SolanaInstrument
from trading.instruments import require_mint

router = APIRouter(dependencies=[Depends(require_local_token)], tags=["simulation"])
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


class BarBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mint: str
    symbol: str
    observed_at: str
    source: str
    close: str | None = None
    open: str | None = None
    high: str | None = None
    low: str | None = None
    volume_quote: str | None = None
    base_volume: str | None = None
    base_reserve: str | None = None
    quote_reserve: str | None = None
    bid: str | None = None
    ask: str | None = None
    bid_size: str | None = None
    ask_size: str | None = None
    security: str | None = None
    creator: str | None = None


class SignalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mint: str
    observed_at: str
    name: str
    reference: str


class MemberBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mint: str
    included: bool
    reason: str


class DatasetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    name: str
    source: str
    selection_note: str
    bars: list[BarBody] = Field(default_factory=list)
    signals: list[SignalBody] = Field(default_factory=list)
    members: list[MemberBody] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class InstrumentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mint: str
    symbol: str
    size_decimals: int
    price_decimals: int
    quote_symbol: str
    quote_decimals: int


class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    strategy: str
    parameters: dict[str, str] = Field(default_factory=dict)
    starting_equity: str
    fee_fixed: str = "0"
    fee_rate: str = "0"
    delay_seconds: int = 0
    max_quote_age_seconds: int = 120
    participation: str = "0.02"
    impact_cap: str = "0.02"
    instruments: list[InstrumentBody]


class WalkBody(RunBody):
    grid: list[dict[str, str]]
    train_bars: int
    test_bars: int
    min_train_trades: int = 1


class CompareBody(RunBody):
    strategies: list[str]


class PaperBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    instrument: InstrumentBody
    side: OrderSide
    quantity: str
    idempotency_key: str
    exit_kind: str = ExitKind.ENTRY.value
    stop_fraction: str | None = None
    signal_ref: str | None = None
    narrative: str = "momentum"
    equity_quote: str | None = None
    sol_balance: str | None = None
    fee_fixed: str = "0"
    fee_rate: str = "0"
    delay_seconds: int = 0
    max_quote_age_seconds: int = 120
    participation: str = "0.02"
    impact_cap: str = "0.02"
    bar: BarBody


def _sim_store(
    request: Request, settings: Settings
) -> MemorySimulationStore | PostgresSimulationRepository:
    injected = getattr(request.app.state, "simulation_store", None)
    if injected is not None:
        return injected
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    return PostgresSimulationRepository(settings)


def _call(action: object) -> object:
    try:
        if not callable(action):
            raise TradingValidationError("The simulation action is not callable.")
        return action()
    except TradingDisabled as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TradingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (DatabaseNotConfiguredError, DatabaseUnavailableError) as exc:
        raise HTTPException(
            status_code=503, detail="Stored simulation records are unavailable."
        ) from exc


def _money(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise HTTPException(status_code=422, detail="A decimal field is invalid.") from exc
    if not parsed.is_finite():
        raise HTTPException(status_code=422, detail="A decimal field is invalid.")
    return parsed


def _moment(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="A timestamp must be ISO-8601.") from exc
    if parsed.tzinfo is None:
        raise HTTPException(status_code=422, detail="A timestamp must include a timezone.")
    return parsed


def _dataset(body: DatasetBody) -> HistoricalDataset:
    return HistoricalDataset(
        dataset_id=body.dataset_id,
        name=body.name,
        source=body.source,
        selection_note=body.selection_note,
        bars=tuple(_bar(item) for item in body.bars),
        signals=tuple(
            HistoricalSignal(item.mint, _moment(item.observed_at), item.name, item.reference)
            for item in body.signals
        ),
        members=tuple(
            UniverseMember(item.mint, item.included, item.reason) for item in body.members
        ),
        limitations=tuple(body.limitations),
    )


def _bar(body: BarBody) -> HistoricalBar:
    return HistoricalBar(
        mint=body.mint,
        symbol=body.symbol,
        observed_at=_moment(body.observed_at),
        source=body.source,
        open=_money(body.open),
        high=_money(body.high),
        low=_money(body.low),
        close=_money(body.close),
        volume_quote=_money(body.volume_quote),
        base_volume=_money(body.base_volume),
        base_reserve=_money(body.base_reserve),
        quote_reserve=_money(body.quote_reserve),
        bid=_money(body.bid),
        ask=_money(body.ask),
        bid_size=_money(body.bid_size),
        ask_size=_money(body.ask_size),
        security=body.security,
        creator=body.creator,
    )


def _instruments(rows: list[InstrumentBody]) -> dict[str, SolanaInstrument]:
    mapped = {
        require_mint(row.mint): SolanaInstrument(
            require_mint(row.mint),
            row.symbol,
            row.size_decimals,
            row.price_decimals,
            row.quote_symbol,
            row.quote_decimals,
        )
        for row in rows
    }
    return mapped


def _spec(
    body: RunBody, dataset: HistoricalDataset, strategy_name: str, parameters: dict[str, str]
) -> BacktestSpec:
    equity = _money(body.starting_equity)
    fixed = _money(body.fee_fixed)
    rate = _money(body.fee_rate)
    participation = _money(body.participation)
    impact = _money(body.impact_cap)
    if None in {equity, fixed, rate, participation, impact}:
        raise HTTPException(status_code=422, detail="A decimal field is invalid.")
    assert equity is not None and fixed is not None and rate is not None
    assert participation is not None and impact is not None
    return BacktestSpec(
        dataset=dataset,
        strategy=strategy_by_name(strategy_name, parameters),
        instruments=_instruments(body.instruments),
        starting_equity=equity,
        schedule=FeeSchedule("configured", fixed, rate),
        latency=LatencyModel(body.delay_seconds, body.max_quote_age_seconds),
        participation=participation,
        impact_cap=impact,
        created_at=datetime.now(UTC),
    )


def _require_paper(settings: Settings) -> None:
    if settings.execution_mode is not ExecutionMode.PAPER:
        raise TradingDisabled("Read-only mode does not run a paper simulation.")


@router.post("/trading/simulation/datasets")
def save_dataset(body: DatasetBody, request: Request, settings: SettingsDep) -> dict[str, object]:
    store = _sim_store(request, settings)

    def action() -> dict[str, object]:
        saved = store.save_dataset(_dataset(body), datetime.now(UTC))
        return {"dataset_id": saved.dataset_id, "bars": len(saved.bars)}

    result = _call(action)
    assert isinstance(result, dict)
    return result


@router.get("/trading/simulation/datasets")
def list_datasets(request: Request, settings: SettingsDep) -> dict[str, object]:
    store = _sim_store(request, settings)
    rows = _call(store.list_datasets)
    assert isinstance(rows, tuple)
    return {"datasets": [{"dataset_id": item[0], "name": item[1]} for item in rows]}


@router.get("/trading/simulation/runs")
def list_runs(request: Request, settings: SettingsDep) -> dict[str, object]:
    store = _sim_store(request, settings)
    rows = _call(store.list_runs)
    assert isinstance(rows, tuple)
    return {"runs": list(rows), "parameters_deployed": False, "live_trading_enabled": False}


@router.post("/trading/simulation/backtests")
def run_saved_backtest(body: RunBody, request: Request, settings: SettingsDep) -> dict[str, object]:
    store = _sim_store(request, settings)

    def action() -> dict[str, object]:
        _require_paper(settings)
        dataset = store.get_dataset(body.dataset_id)
        if dataset is None:
            raise TradingValidationError("That dataset is not stored.")
        report = run_backtest(_spec(body, dataset, body.strategy, body.parameters))
        store.save_run(report)
        return dump_report(report)

    result = _call(action)
    assert isinstance(result, dict)
    return result


@router.post("/trading/simulation/walk-forward")
def run_walk(body: WalkBody, request: Request, settings: SettingsDep) -> dict[str, object]:
    store = _sim_store(request, settings)

    def action() -> dict[str, object]:
        _require_paper(settings)
        dataset = store.get_dataset(body.dataset_id)
        if dataset is None:
            raise TradingValidationError("That dataset is not stored.")
        report = walk_forward(
            _spec(body, dataset, body.strategy, {}),
            tuple(body.grid),
            train_bars=body.train_bars,
            test_bars=body.test_bars,
            min_train_trades=body.min_train_trades,
        )
        store.save_run(report)
        return dump_report(report)

    result = _call(action)
    assert isinstance(result, dict)
    return result


@router.post("/trading/simulation/comparisons")
def run_comparison(body: CompareBody, request: Request, settings: SettingsDep) -> dict[str, object]:
    store = _sim_store(request, settings)

    def action() -> dict[str, object]:
        _require_paper(settings)
        dataset = store.get_dataset(body.dataset_id)
        if dataset is None:
            raise TradingValidationError("That dataset is not stored.")
        strategies = tuple(strategy_by_name(name, body.parameters) for name in body.strategies)
        report = compare_strategies(
            _spec(body, dataset, body.strategies[0], body.parameters), strategies
        )
        store.save_run(report)
        return dump_report(report)

    result = _call(action)
    assert isinstance(result, dict)
    return result


@router.post("/trading/simulation/paper")
def submit_modeled_paper(
    body: PaperBody, request: Request, settings: SettingsDep
) -> dict[str, object]:
    """Price one paper order and submit it through Shield. The ledger stays simulated."""

    sim = _sim_store(request, settings)
    store = _store(request, settings)
    clock = _clock(request)

    def action() -> dict[str, object]:
        _require_paper(settings)
        fixed = _money(body.fee_fixed)
        rate = _money(body.fee_rate)
        participation = _money(body.participation)
        impact = _money(body.impact_cap)
        if None in {fixed, rate, participation, impact}:
            raise HTTPException(status_code=422, detail="A decimal field is invalid.")
        assert (
            fixed is not None
            and rate is not None
            and participation is not None
            and impact is not None
        )
        broker = PaperBroker(
            settings.execution_mode,
            store,
            clock,
            FeeSchedule("configured", fixed, rate),
            LatencyModel(body.delay_seconds, body.max_quote_age_seconds),
            participation=participation,
            impact_cap=impact,
        )
        result = broker.execute(
            BrokerCommand(
                strategy_id=body.strategy_id,
                instrument=_instruments([body.instrument])[require_mint(body.instrument.mint)],
                side=body.side,
                quantity=_money(body.quantity) or Decimal(0),
                bar=_bar(body.bar),
                exit_kind=body.exit_kind,
                stop_fraction=_money(body.stop_fraction),
                signal_ref=body.signal_ref,
                idempotency_key=body.idempotency_key,
                narrative=body.narrative,
                equity_quote=_money(body.equity_quote),
                sol_balance=_money(body.sol_balance),
                marks=(),
            )
        )
        if result.assumption is not None:
            sim.save_assumption(result.assumption, clock())
        order = result.order
        return {
            "refusal": result.refusal,
            "simulated": True,
            "live_trading_enabled": False,
            "client_order_id": None if order is None else order.client_order_id,
            "shield_decision": None if order is None else order.shield_decision,
            "state": None if order is None else order.state.value,
            "fill_price": None
            if order is None or order.fill_price is None
            else str(order.fill_price),
        }

    result = _call(action)
    assert isinstance(result, dict)
    return result
