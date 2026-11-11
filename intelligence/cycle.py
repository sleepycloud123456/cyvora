"""One read-only radar cycle.

The cycle calls the existing GMGN services. It does not add endpoints, sign,
or submit a trade. Request weight is counted before each call and stops at
the configured budget. The free plan's limiter paces whatever is sent. A
server rate-limit response ends further requests in that cycle.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from config.settings import Settings
from integrations.gmgn.client import GMGNClient, client_from_settings
from integrations.gmgn.constants import route_weight
from integrations.gmgn.errors import GMGNError, GMGNRateLimitError, GMGNTransportError
from integrations.gmgn.models import LaunchToken, TrendingToken
from integrations.gmgn.read_only import GMGNReadOnly
from integrations.gmgn.validation import require_address
from intelligence.numbers import as_decimal
from intelligence.opportunity import (
    CandlePoint,
    ScoreInputs,
    TokenScore,
    candle_is_stale,
    candles_from_gmgn,
    explain_score,
    rank_results,
    score_token,
)
from intelligence.store import AnalysisRecord, DiscoveryRecord, RadarStore, StoredCycle

_INFO = route_weight("GET", "/v1/token/info", {})
_SECURITY = route_weight("GET", "/v1/token/security", {})
_POOL = route_weight("GET", "/v1/token/pool_info", {})
_HOLDERS = route_weight("GET", "/v1/market/token_top_holders", {})
_TRADERS = route_weight("GET", "/v1/market/token_top_traders", {})
_RANK = route_weight("GET", "/v1/market/rank", {})
_TRENCHES = route_weight("POST", "/v1/trenches", {})


@dataclass(frozen=True, slots=True)
class CycleResult:
    """Public outcome of one cycle. Text here is safe to print."""

    cycle_id: int | None
    status: str
    weight_used: int
    request_count: int
    trending_count: int
    launch_count: int
    analysed_count: int
    rate_limit_hits: int
    lines: tuple[str, ...]
    error_code: str | None

    def public_report(self) -> str:
        header = [
            "RADAR_CYCLE_OK"
            if self.cycle_id is not None and self.analysed_count
            else "RADAR_CYCLE_PARTIAL",
            f"cycle_id={self.cycle_id if self.cycle_id is not None else 'none'}",
            f"status={self.status}",
            f"weight_used={self.weight_used}",
            f"requests={self.request_count}",
            f"trending={self.trending_count}",
            f"launches={self.launch_count}",
            f"analysed={self.analysed_count}",
            f"rate_limit_hits={self.rate_limit_hits}",
            f"error_code={self.error_code or 'none'}",
            "entry=not_authorized",
        ]
        if self.status == "failed" and self.cycle_id is None:
            header[0] = "RADAR_CYCLE_FAIL"
        return "\n".join([*header, *self.lines])


@dataclass
class _Budget:
    limit: int
    used: int = 0
    requests: int = 0
    rate_limit_hits: int = 0
    failures: list[str] = field(default_factory=list)

    def take(self, weight: int) -> bool:
        if self.used + weight > self.limit:
            return False
        self.used += weight
        self.requests += 1
        return True


@dataclass
class _Candidate:
    chain: str
    address: str
    symbol: str | None
    name: str | None
    sources: list[str]
    price: Decimal | None
    market_cap: Decimal | None
    liquidity: Decimal | None
    volume: Decimal | None
    holder_count: int | None
    creation_timestamp: int | None
    price_change: Decimal | None
    rank_extra: dict[str, object] | None


async def run_radar_cycle(
    settings: Settings,
    store: RadarStore,
    *,
    client: GMGNClient | None = None,
    now: datetime | None = None,
) -> CycleResult:
    """Discover, analyse, score, rank, and store one Solana cycle."""

    moment = now or datetime.now(UTC)
    budget = _Budget(settings.radar_budget_weight)
    owns_client = client is None
    active = client or client_from_settings(settings)
    discoveries: list[DiscoveryRecord] = []
    analyses: list[AnalysisRecord] = []
    suggestions: list[tuple[str, str, str | None]] = []
    trending_count = 0
    launch_count = 0
    status = "failed"
    error_code: str | None = None
    try:
        surface = GMGNReadOnly(active)
        candidates, trending_count, launch_count = await _discover(
            settings,
            surface,
            budget,
            moment,
            discoveries,
        )
        changes = tuple(
            row.price_change
            for row in discoveries
            if row.source == "trending" and row.price_change is not None
        )
        selected = _select(candidates, settings.radar_analyse_limit)
        scored: list[_Analysed] = []
        for candidate in selected:
            analysed = await _analyse(settings, surface, store, budget, candidate, changes, moment)
            if analysed is not None:
                scored.append(analysed)
        ranked_inputs = [(item, item.score, item.candidate.address) for item in scored]
        for rank, item, _result in rank_results(ranked_inputs):
            explanation = explain_score(item.candidate.symbol, item.score)
            analyses.append(_analysis_record(item, explanation, rank))
            if item.score.lifecycle == "watch_suggested":
                suggestions.append(
                    (item.candidate.chain, item.candidate.address, item.candidate.symbol)
                )
        status = _status(trending_count, launch_count, len(analyses), budget.failures)
    except Exception as exc:
        error_code = type(exc).__name__
        status = "failed"
        budget.failures.append(f"cycle:{error_code}")
    finally:
        if owns_client:
            await active.aclose()

    note = _note(settings, budget)
    stored = StoredCycle(
        chain=settings.radar_chain,
        status=status,
        started_at=moment,
        finished_at=datetime.now(UTC),
        weight_budget=settings.radar_budget_weight,
        weight_used=budget.used,
        request_count=budget.requests,
        trending_count=trending_count,
        launch_count=launch_count,
        analysed_count=len(analyses),
        error_code=error_code,
        note=note,
        kline_resolution=settings.radar_kline_resolution,
        discoveries=tuple(discoveries),
        analyses=tuple(analyses),
        watch_suggestions=tuple(suggestions),
    )
    cycle_id: int | None
    try:
        cycle_id = store.save_cycle(stored)
    except Exception as exc:
        cycle_id = None
        status = "failed"
        error_code = type(exc).__name__
    lines = tuple(_line(row) for row in analyses)
    return CycleResult(
        cycle_id=cycle_id,
        status=status,
        weight_used=budget.used,
        request_count=budget.requests,
        trending_count=trending_count,
        launch_count=launch_count,
        analysed_count=len(analyses),
        rate_limit_hits=budget.rate_limit_hits,
        lines=lines,
        error_code=error_code,
    )


async def _discover(
    settings: Settings,
    surface: GMGNReadOnly,
    budget: _Budget,
    moment: datetime,
    discoveries: list[DiscoveryRecord],
) -> tuple[dict[tuple[str, str], _Candidate], int, int]:
    candidates: dict[tuple[str, str], _Candidate] = {}
    trending = await _read(
        budget,
        _RANK,
        "trending",
        lambda: surface.discovery.trending(
            settings.radar_chain,
            settings.radar_rank_interval,
            limit=settings.radar_trending_limit,
        ),
    )
    launches = await _read(
        budget,
        _TRENCHES,
        "new_launches",
        lambda: surface.discovery.new_launches(
            settings.radar_chain, limit=settings.radar_launch_limit
        ),
    )
    trending_rows = () if trending is None else tuple(trending.payload)
    launch_rows = () if launches is None else tuple(launches.payload)
    for trending_row in trending_rows:
        _add_trending(candidates, discoveries, trending_row, settings.radar_chain, moment)
    for launch_row in launch_rows:
        _add_launch(candidates, discoveries, launch_row, settings.radar_chain, moment)
    return candidates, len(trending_rows), len(launch_rows)


@dataclass(slots=True)
class _Analysed:
    candidate: _Candidate
    score: TokenScore
    candles: tuple[CandlePoint, ...]
    routes: tuple[str, ...]
    freshness: str


async def _analyse(
    settings: Settings,
    surface: GMGNReadOnly,
    store: RadarStore,
    budget: _Budget,
    candidate: _Candidate,
    changes: tuple[Decimal, ...],
    moment: datetime,
) -> _Analysed | None:
    chain = candidate.chain
    address = candidate.address
    routes: list[str] = []
    info = await _read(budget, _INFO, "token_info", lambda: surface.tokens.info(chain, address))
    security = await _read(
        budget,
        _SECURITY,
        "token_security",
        lambda: surface.tokens.security(chain, address),
    )
    pool = await _read(budget, _POOL, "pool_info", lambda: surface.tokens.pool(chain, address))
    kline_weight = route_weight(
        "GET",
        "/v1/market/token_kline",
        {"resolution": settings.radar_kline_resolution},
    )
    to_unix = int(moment.timestamp())
    from_unix = to_unix - settings.radar_kline_lookback_seconds
    candles = await _read(
        budget,
        kline_weight,
        "kline",
        lambda: surface.market.candles(
            chain,
            address,
            settings.radar_kline_resolution,
            from_unix=from_unix,
            to_unix=to_unix,
        ),
    )
    holders = None
    if budget.used + _HOLDERS <= budget.limit:
        holders = await _read(
            budget,
            _HOLDERS,
            "holders",
            lambda: surface.tokens.holders(chain, address, limit=10),
        )
    traders = None
    if budget.used + _TRADERS <= budget.limit:
        traders = await _read(
            budget,
            _TRADERS,
            "traders",
            lambda: surface.tokens.traders(chain, address, limit=10, order_by="profit"),
        )
    if info is None and security is None and pool is None and candles is None:
        return None
    if info is not None:
        routes.append("GET /v1/token/info")
        _apply_info(candidate, info.payload)
    if security is not None:
        routes.append("GET /v1/token/security")
    if pool is not None:
        routes.append("GET /v1/token/pool_info")
    points = () if candles is None else candles_from_gmgn(candles.payload)
    if candles is not None:
        routes.append("GET /v1/market/token_kline")
    if holders is not None:
        routes.append("GET /v1/market/token_top_holders")
    if traders is not None:
        routes.append("GET /v1/market/token_top_traders")
    stale = candle_is_stale(points, now_unix=to_unix, resolution=settings.radar_kline_resolution)
    has_time = any(point.time is not None for point in points)
    if not points or not has_time:
        freshness = "unknown"
    elif stale:
        freshness = "stale"
    else:
        freshness = "fresh"
    scored = score_token(
        ScoreInputs(
            security=None if security is None else security.payload,
            info=None if info is None else info.payload,
            pool=None if pool is None else pool.payload,
            candles=points,
            holders=None if holders is None else tuple(holders.payload),
            traders=None if traders is None else tuple(traders.payload),
            rank_changes=changes,
            rank_extra=candidate.rank_extra,
            stale_candles=stale,
            discovered_liquidity=candidate.liquidity,
            prior_liquidity=store.latest_liquidity(chain, address),
            sources=tuple(candidate.sources),
        )
    )
    return _Analysed(candidate, scored, points, tuple(routes), freshness)


def _apply_info(candidate: _Candidate, info: object) -> None:
    from integrations.gmgn.models import TokenInfo

    if not isinstance(info, TokenInfo):
        return
    if info.price is not None and info.price.price is not None:
        candidate.price = info.price.price
    if info.holder_count is not None:
        candidate.holder_count = info.holder_count
    if info.creation_timestamp is not None:
        candidate.creation_timestamp = info.creation_timestamp
    if info.symbol:
        candidate.symbol = _clip(info.symbol, 64)
    if info.name:
        candidate.name = _clip(info.name, 256)
    if info.liquidity is not None and candidate.liquidity is None:
        candidate.liquidity = info.liquidity


def _analysis_record(item: _Analysed, explanation: str, rank: int) -> AnalysisRecord:
    candidate = item.candidate
    liquidity = item.score.liquidity.figure
    if liquidity is None:
        liquidity = candidate.liquidity
    return AnalysisRecord(
        chain=candidate.chain,
        address=candidate.address,
        symbol=_clip(candidate.symbol, 64),
        name=_clip(candidate.name, 256),
        price=candidate.price,
        market_cap=candidate.market_cap,
        liquidity=liquidity,
        volume=candidate.volume,
        holder_count=candidate.holder_count,
        creation_timestamp=candidate.creation_timestamp,
        sources=tuple(candidate.sources),
        routes=item.routes,
        freshness=item.freshness,
        score=item.score,
        candles=item.candles,
        explanation=explanation[:4000],
        rank=rank,
    )


async def _read[T](
    budget: _Budget,
    weight: int,
    label: str,
    factory: Callable[[], Awaitable[T]],
) -> T | None:
    if budget.rate_limit_hits:
        budget.failures.append(f"{label}:paused")
        return None
    if not budget.take(weight):
        budget.failures.append(f"{label}:budget")
        return None
    try:
        return await factory()
    except GMGNRateLimitError:
        budget.rate_limit_hits += 1
        budget.failures.append(f"{label}:GMGNRateLimitError")
    except GMGNTransportError:
        budget.failures.append(f"{label}:GMGNTransportError")
        if budget.take(weight):
            try:
                return await factory()
            except GMGNRateLimitError:
                budget.rate_limit_hits += 1
                budget.failures.append(f"{label}:GMGNRateLimitError")
            except GMGNError as exc:
                budget.failures.append(f"{label}:retry_{type(exc).__name__}")
    except GMGNError as exc:
        budget.failures.append(f"{label}:{type(exc).__name__}")
    return None


def _add_trending(
    candidates: dict[tuple[str, str], _Candidate],
    discoveries: list[DiscoveryRecord],
    row: TrendingToken,
    chain: str,
    moment: datetime,
) -> None:
    address = _address(row.address, chain)
    if address is None:
        return
    change = _price_change(row)
    extra = dict(row.model_extra or {})
    _merge(
        candidates,
        _Candidate(
            chain=chain,
            address=address,
            symbol=_clip(row.symbol, 64),
            name=_clip(row.name, 256),
            sources=["trending"],
            price=row.price,
            market_cap=row.market_cap,
            liquidity=row.liquidity,
            volume=row.volume,
            holder_count=row.holder_count,
            creation_timestamp=row.creation_timestamp or row.open_timestamp,
            price_change=change,
            rank_extra=extra,
        ),
    )
    discoveries.append(
        DiscoveryRecord(
            source="trending",
            chain=chain,
            address=address,
            symbol=_clip(row.symbol, 64),
            name=_clip(row.name, 256),
            price=row.price,
            market_cap=row.market_cap,
            liquidity=row.liquidity,
            volume=row.volume,
            holder_count=row.holder_count,
            creation_timestamp=row.creation_timestamp or row.open_timestamp,
            route="GET /v1/market/rank",
            retrieved_at=moment,
            price_change=change,
        )
    )


def _add_launch(
    candidates: dict[tuple[str, str], _Candidate],
    discoveries: list[DiscoveryRecord],
    row: LaunchToken,
    chain: str,
    moment: datetime,
) -> None:
    address = _address(row.address, chain)
    if address is None:
        return
    _merge(
        candidates,
        _Candidate(
            chain=chain,
            address=address,
            symbol=_clip(row.symbol, 64),
            name=_clip(row.name, 256),
            sources=["new_launch"],
            price=None,
            market_cap=row.usd_market_cap,
            liquidity=row.liquidity,
            volume=None,
            holder_count=row.holder_count,
            creation_timestamp=row.created_timestamp,
            price_change=None,
            rank_extra=None,
        ),
    )
    discoveries.append(
        DiscoveryRecord(
            source="new_launch",
            chain=chain,
            address=address,
            symbol=_clip(row.symbol, 64),
            name=_clip(row.name, 256),
            price=None,
            market_cap=row.usd_market_cap,
            liquidity=row.liquidity,
            volume=None,
            holder_count=row.holder_count,
            creation_timestamp=row.created_timestamp,
            route="POST /v1/trenches",
            retrieved_at=moment,
            price_change=None,
        )
    )


def _merge(candidates: dict[tuple[str, str], _Candidate], incoming: _Candidate) -> None:
    key = (incoming.chain, incoming.address)
    current = candidates.get(key)
    if current is None:
        candidates[key] = incoming
        return
    for source in incoming.sources:
        if source not in current.sources:
            current.sources.append(source)
    current.price = current.price if current.price is not None else incoming.price
    current.market_cap = (
        current.market_cap if current.market_cap is not None else incoming.market_cap
    )
    current.liquidity = current.liquidity if current.liquidity is not None else incoming.liquidity
    current.volume = current.volume if current.volume is not None else incoming.volume
    current.holder_count = (
        current.holder_count if current.holder_count is not None else incoming.holder_count
    )
    current.creation_timestamp = (
        current.creation_timestamp
        if current.creation_timestamp is not None
        else incoming.creation_timestamp
    )
    current.price_change = (
        current.price_change if current.price_change is not None else incoming.price_change
    )
    if current.rank_extra is None:
        current.rank_extra = incoming.rank_extra


def _select(candidates: dict[tuple[str, str], _Candidate], limit: int) -> list[_Candidate]:
    ordered = sorted(
        candidates.values(),
        key=lambda item: (
            0 if len(item.sources) > 1 else 1,
            0 if "trending" in item.sources else 1,
            item.address,
        ),
    )
    return ordered[:limit]


def _price_change(row: TrendingToken) -> Decimal | None:
    if row.price_change_percent is not None:
        return row.price_change_percent
    extra = row.model_extra or {}
    for key in ("change1h", "change5m", "change1m"):
        parsed = as_decimal(extra.get(key))
        if parsed is not None:
            return parsed
    return None


def _address(value: str | None, chain: str) -> str | None:
    if value is None:
        return None
    try:
        return require_address(value, chain)
    except GMGNError:
        return None


def _clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = "".join(char for char in value if char.isprintable())
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    return cleaned[:limit]


def _status(trending: int, launches: int, analysed: int, failures: list[str]) -> str:
    if trending == 0 and launches == 0:
        return "failed"
    if analysed == 0 or failures:
        return "partial"
    return "completed"


def _note(settings: Settings, budget: _Budget) -> str:
    failure_text = ",".join(budget.failures[:8]) or "none"
    text = (
        f"retention_days={settings.radar_market_retention_days}; "
        f"plan={settings.gmgn_plan}; failures={failure_text}"
    )
    return text[:500]


def _line(row: AnalysisRecord) -> str:
    symbol = row.symbol or "-"
    total = "unknown" if row.score.total is None else str(row.score.total)
    return (
        f"rank={row.rank} symbol={symbol} address={row.address} "
        f"decision={row.score.decision} score={total} "
        f"security={row.score.security.category} liquidity={row.score.liquidity.status} "
        f"smart_money={row.score.smart_money.status} whales={row.score.whales.status} "
        f"entry={row.score.entry_consideration}"
    )
