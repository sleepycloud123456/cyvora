"""Radar and watchlist routes. They do not submit orders."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from apps.api.auth import require_local_token
from apps.api.dependencies import get_app_settings
from config.settings import Settings
from database.repositories.radar import PostgresRadarRepository
from domain.exceptions import DatabaseNotConfiguredError, DatabaseUnavailableError
from integrations.gmgn.errors import GMGNNotConfigured, GMGNValidationError
from integrations.gmgn.validation import require_address, require_chain
from intelligence.cycle import CycleResult, run_radar_cycle
from intelligence.store import AnalysisDetail, CycleSnapshot, RadarStore, RankRow, WatchRow

router = APIRouter(dependencies=[Depends(require_local_token)], tags=["radar"])
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


class RankModel(BaseModel):
    rank: int
    chain: str
    address: str
    symbol: str | None
    name: str | None
    price: str | None
    market_cap: str | None
    liquidity: str | None
    volume: str | None
    price_change: str | None
    volume_change: str | None
    smart_money: str
    security_category: str
    score: str | None
    research_confidence: str | None
    entry_consideration: str
    decision: str
    warnings: list[str]


class DetailModel(BaseModel):
    chain: str
    address: str
    symbol: str | None
    explanation: str
    decision: str
    score: str | None
    security_category: str
    liquidity_status: str
    smart_money_status: str
    whale_status: str
    components: list[list[str]]
    warnings: list[str]


class WatchModel(BaseModel):
    chain: str
    address: str
    symbol: str | None
    note: str
    source: str
    active: bool


class CycleModel(BaseModel):
    cycle_id: int
    status: str
    started_at: str
    finished_at: str | None
    chain: str
    weight_used: int
    request_count: int
    trending_count: int
    launch_count: int
    analysed_count: int
    note: str | None
    rankings: list[RankModel]
    analyses: list[DetailModel]
    watches: list[WatchModel]
    entry_consideration: str = "not_authorized"


class LatestModel(BaseModel):
    cycle: CycleModel | None
    entry_consideration: str = "not_authorized"


class RunModel(BaseModel):
    cycle_id: int | None
    status: str
    analysed_count: int
    entry_consideration: str = "not_authorized"


class WatchBody(BaseModel):
    chain: str = "sol"
    address: str = Field(min_length=32, max_length=44)
    symbol: str | None = None
    note: str = "Added from the local API. This is not an entry."


class Runner(Protocol):
    def __call__(self, settings: Settings, store: RadarStore) -> Awaitable[CycleResult]:
        """Run one read-only cycle against the supplied store."""


def _store(request: Request, settings: Settings) -> RadarStore:
    injected = getattr(request.app.state, "radar_store", None)
    if injected is not None:
        return injected
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    return PostgresRadarRepository(settings)


def _cycle_model(snapshot: CycleSnapshot) -> CycleModel:
    return CycleModel(
        cycle_id=snapshot.cycle_id,
        status=snapshot.status,
        started_at=snapshot.started_at,
        finished_at=snapshot.finished_at,
        chain=snapshot.chain,
        weight_used=snapshot.weight_used,
        request_count=snapshot.request_count,
        trending_count=snapshot.trending_count,
        launch_count=snapshot.launch_count,
        analysed_count=snapshot.analysed_count,
        note=snapshot.note,
        rankings=[_rank(row) for row in snapshot.rankings],
        analyses=[_detail(row) for row in snapshot.analyses],
        watches=[_watch(row) for row in snapshot.watches],
    )


def _rank(row: RankRow) -> RankModel:
    return RankModel(
        rank=row.rank,
        chain=row.chain,
        address=row.address,
        symbol=row.symbol,
        name=row.name,
        price=row.price,
        market_cap=row.market_cap,
        liquidity=row.liquidity,
        volume=row.volume,
        price_change=row.price_change,
        volume_change=row.volume_change,
        smart_money=row.smart_money,
        security_category=row.security_category,
        score=row.score,
        research_confidence=row.research_confidence,
        entry_consideration=row.entry_consideration,
        decision=row.decision,
        warnings=list(row.warnings),
    )


def _detail(row: AnalysisDetail) -> DetailModel:
    return DetailModel(
        chain=row.chain,
        address=row.address,
        symbol=row.symbol,
        explanation=row.explanation,
        decision=row.decision,
        score=row.score,
        security_category=row.security_category,
        liquidity_status=row.liquidity_status,
        smart_money_status=row.smart_money_status,
        whale_status=row.whale_status,
        components=[list(item) for item in row.components],
        warnings=list(row.warnings),
    )


def _watch(row: WatchRow) -> WatchModel:
    return WatchModel(
        chain=row.chain,
        address=row.address,
        symbol=row.symbol,
        note=row.note,
        source=row.source,
        active=row.active,
    )


@router.get("/radar/latest", response_model=LatestModel)
def latest_cycle(
    request: Request,
    settings: SettingsDep,
) -> LatestModel:
    """Return the newest stored cycle. This route does not call GMGN."""

    try:
        snapshot = _store(request, settings).latest_snapshot()
    except (DatabaseNotConfiguredError, DatabaseUnavailableError) as exc:
        raise HTTPException(
            status_code=503, detail="Stored radar results are unavailable."
        ) from exc
    if snapshot is None:
        return LatestModel(cycle=None)
    return LatestModel(cycle=_cycle_model(snapshot))


@router.post("/radar/cycles", response_model=RunModel)
async def run_cycle(
    request: Request,
    settings: SettingsDep,
) -> RunModel:
    """Run one read-only cycle and store it."""

    store = _store(request, settings)
    runner: Runner | None = getattr(request.app.state, "radar_runner", None)
    try:
        if runner is not None:
            result = await runner(settings, store)
        else:
            if settings.gmgn_api_key is None:
                raise HTTPException(status_code=503, detail="GMGN is not configured.")
            async with request.app.state.radar_lock:
                result = await run_radar_cycle(settings, store)
    except GMGNNotConfigured as exc:
        raise HTTPException(status_code=503, detail="GMGN is not configured.") from exc
    except (DatabaseNotConfiguredError, DatabaseUnavailableError) as exc:
        raise HTTPException(
            status_code=503, detail="Stored radar results are unavailable."
        ) from exc
    return RunModel(
        cycle_id=result.cycle_id,
        status=result.status,
        analysed_count=result.analysed_count,
    )


@router.post("/radar/watchlist", response_model=WatchModel)
def add_watch(
    body: WatchBody,
    request: Request,
    settings: SettingsDep,
) -> WatchModel:
    try:
        chain = require_chain(body.chain)
        address = require_address(body.address, chain)
    except GMGNValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid chain or address.") from exc
    try:
        row = _store(request, settings).add_watch(chain, address, body.symbol, body.note, "manual")
    except (DatabaseNotConfiguredError, DatabaseUnavailableError) as exc:
        raise HTTPException(status_code=503, detail="The watchlist could not be updated.") from exc
    return _watch(row)


@router.delete("/radar/watchlist/{chain}/{address}")
def remove_watch(
    chain: str,
    address: str,
    request: Request,
    settings: SettingsDep,
) -> dict[str, bool]:
    try:
        checked_chain = require_chain(chain)
        checked_address = require_address(address, checked_chain)
        removed = _store(request, settings).deactivate_watch(checked_chain, checked_address)
    except GMGNValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid chain or address.") from exc
    except (DatabaseNotConfiguredError, DatabaseUnavailableError) as exc:
        raise HTTPException(status_code=503, detail="The watchlist could not be updated.") from exc
    return {"removed": removed}
