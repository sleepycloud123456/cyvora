"""PostgreSQL implementation of the radar store."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from config.settings import Settings
from database.connection import create_database_engine
from database.models.radar import (
    AuditEvent,
    IndicatorSignal,
    LiquiditySnapshot,
    RadarCycle,
    SecurityAssessmentRow,
    SmartMoneyEvent,
    Token,
    TokenAnalysis,
    TokenCandle,
    TokenObservation,
    WatchlistItem,
    WhaleEvent,
)
from domain.exceptions import DatabaseNotConfiguredError, DatabaseUnavailableError
from intelligence.numbers import format_decimal
from intelligence.store import (
    AnalysisDetail,
    AnalysisRecord,
    CycleSnapshot,
    DiscoveryRow,
    RankRow,
    StoredCycle,
    WatchRow,
)

logger = logging.getLogger("cyvora.radar")

_WATCH_NOTE = (
    "Radar suggested this token because the documented score threshold was met. "
    "This is not an entry."
)


class PostgresRadarRepository:
    """Insert radar history and read it back for the terminal."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def save_cycle(self, cycle: StoredCycle) -> int:
        engine = _engine(self._settings)
        try:
            with Session(engine) as session:
                cycle_id = _save(session, cycle)
                session.commit()
                return cycle_id
        except (DatabaseNotConfiguredError, DatabaseUnavailableError):
            raise
        except Exception as exc:
            logger.warning("radar persist failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Radar results could not be stored.") from None
        finally:
            engine.dispose()

    def latest_snapshot(self) -> CycleSnapshot | None:
        engine = _engine(self._settings)
        try:
            with Session(engine) as session:
                cycle = session.scalar(select(RadarCycle).order_by(RadarCycle.id.desc()).limit(1))
                if cycle is None:
                    return None
                return _snapshot(session, cycle)
        except DatabaseNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("radar load failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Stored radar results could not be read.") from None
        finally:
            engine.dispose()

    def latest_liquidity(self, chain: str, address: str) -> Decimal | None:
        engine = _engine(self._settings)
        try:
            with Session(engine) as session:
                value = session.scalar(
                    select(LiquiditySnapshot.liquidity)
                    .join(Token, Token.id == LiquiditySnapshot.token_id)
                    .where(
                        Token.chain == chain,
                        Token.address == address,
                        LiquiditySnapshot.liquidity.is_not(None),
                    )
                    .order_by(LiquiditySnapshot.retrieved_at.desc())
                    .limit(1)
                )
                return value if isinstance(value, Decimal) else None
        finally:
            engine.dispose()

    def add_watch(
        self,
        chain: str,
        address: str,
        symbol: str | None,
        note: str,
        source: str,
    ) -> WatchRow:
        engine = _engine(self._settings)
        try:
            with Session(engine) as session:
                row = _upsert_watch(
                    session, chain, address, symbol, note[:500], source, active=True
                )
                session.add(
                    AuditEvent(
                        action="watchlist_add",
                        result="stored",
                        subject=f"{chain}:{address}"[:160],
                        detail=f"Watch source {source[:40]}.",
                    )
                )
                session.commit()
                return row
        except (DatabaseNotConfiguredError, DatabaseUnavailableError):
            raise
        except Exception as exc:
            logger.warning("watchlist add failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The watchlist could not be updated.") from None
        finally:
            engine.dispose()

    def list_watches(self) -> tuple[WatchRow, ...]:
        engine = _engine(self._settings)
        try:
            with Session(engine) as session:
                items = session.scalars(select(WatchlistItem).order_by(WatchlistItem.id)).all()
                return tuple(_watch(item) for item in items)
        except DatabaseNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("watchlist load failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The watchlist could not be read.") from None
        finally:
            engine.dispose()

    def deactivate_watch(self, chain: str, address: str) -> bool:
        engine = _engine(self._settings)
        try:
            with Session(engine) as session:
                item = session.scalar(
                    select(WatchlistItem).where(
                        WatchlistItem.chain == chain,
                        WatchlistItem.address == address,
                    )
                )
                if item is None or not item.active:
                    return False
                item.active = False
                session.add(
                    AuditEvent(
                        action="watchlist_remove",
                        result="inactive",
                        subject=f"{chain}:{address}"[:160],
                        detail="Watch row kept and marked inactive.",
                    )
                )
                session.commit()
                return True
        except (DatabaseNotConfiguredError, DatabaseUnavailableError):
            raise
        except Exception as exc:
            logger.warning("watchlist remove failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The watchlist could not be updated.") from None
        finally:
            engine.dispose()


def _save(session: Session, cycle: StoredCycle) -> int:
    row = RadarCycle(
        chain=cycle.chain,
        status=cycle.status,
        started_at=cycle.started_at,
        finished_at=cycle.finished_at,
        weight_budget=cycle.weight_budget,
        weight_used=cycle.weight_used,
        request_count=cycle.request_count,
        trending_count=cycle.trending_count,
        launch_count=cycle.launch_count,
        analysed_count=cycle.analysed_count,
        error_code=cycle.error_code,
        note=None if cycle.note is None else cycle.note[:500],
        kline_resolution=cycle.kline_resolution,
    )
    session.add(row)
    session.flush()
    changes = {(item.chain, item.address): item.price_change for item in cycle.discoveries}
    for discovery in cycle.discoveries:
        token = _token(
            session,
            discovery.chain,
            discovery.address,
            discovery.symbol,
            discovery.name,
            discovery.retrieved_at,
        )
        session.add(
            TokenObservation(
                token_id=token.id,
                cycle_id=row.id,
                source=discovery.source,
                route=discovery.route,
                retrieved_at=discovery.retrieved_at,
                price=discovery.price,
                market_cap=discovery.market_cap,
                liquidity=discovery.liquidity,
                volume=discovery.volume,
                holder_count=discovery.holder_count,
                creation_timestamp=discovery.creation_timestamp,
                price_change=discovery.price_change,
            )
        )
    for analysis in cycle.analyses:
        token = _token(
            session,
            analysis.chain,
            analysis.address,
            analysis.symbol,
            analysis.name,
            cycle.finished_at,
        )
        _write_analysis(
            session, row, token, analysis, changes.get((analysis.chain, analysis.address))
        )
    for chain, address, symbol in cycle.watch_suggestions:
        current = session.scalar(
            select(WatchlistItem).where(
                WatchlistItem.chain == chain, WatchlistItem.address == address
            )
        )
        if current is not None and current.active:
            session.add(
                AuditEvent(
                    action="watch_suggestion",
                    result="skipped",
                    subject=f"{chain}:{address}"[:160],
                    detail="An active watch already exists.",
                )
            )
            continue
        _upsert_watch(session, chain, address, symbol, _WATCH_NOTE, "radar_suggestion", active=True)
        session.add(
            AuditEvent(
                action="watch_suggestion",
                result="stored",
                subject=f"{chain}:{address}"[:160],
                detail="Score threshold met. Entry was not authorized.",
            )
        )
    session.add(
        AuditEvent(
            action="radar_cycle",
            result=cycle.status,
            subject=f"cycle:{row.id}",
            detail=(
                f"Discovered trending {cycle.trending_count}, launches {cycle.launch_count}, "
                f"analysed {cycle.analysed_count}."
            )[:500],
        )
    )
    session.flush()
    return row.id


def _write_analysis(
    session: Session,
    cycle: RadarCycle,
    token: Token,
    analysis: AnalysisRecord,
    price_change: Decimal | None,
) -> None:
    score = analysis.score
    session.add(
        TokenAnalysis(
            token_id=token.id,
            cycle_id=cycle.id,
            rank_position=analysis.rank,
            decision=score.decision,
            total_score=score.total,
            confidence=score.research_confidence,
            security_category=score.security.category,
            liquidity_status=score.liquidity.status,
            liquidity=analysis.liquidity,
            freshness=analysis.freshness,
            lifecycle=score.lifecycle,
            explanation=analysis.explanation,
            breakdown=_breakdown(analysis, price_change),
        )
    )
    session.add(
        SecurityAssessmentRow(
            token_id=token.id,
            cycle_id=cycle.id,
            category=score.security.category,
            score=score.security.score,
            evidence=[list(pair) for pair in score.security.evidence],
            missing=list(score.security.missing),
            warnings=list(score.security.warnings),
        )
    )
    session.add(
        LiquiditySnapshot(
            token_id=token.id,
            cycle_id=cycle.id,
            retrieved_at=cycle.finished_at,
            status=score.liquidity.status,
            liquidity=score.liquidity.figure,
            burn_claim=score.liquidity.burn_claim,
            price_impact=score.liquidity.price_impact,
            evidence=[list(pair) for pair in score.liquidity.evidence],
            warnings=list(score.liquidity.warnings),
        )
    )
    for component in score.components:
        session.add(
            IndicatorSignal(
                token_id=token.id,
                cycle_id=cycle.id,
                name=component.name,
                quality=component.quality,
                score=component.score,
                weight=component.weight,
                detail=component.detail[:4000],
            )
        )
    smart = score.smart_money
    session.add(
        SmartMoneyEvent(
            token_id=token.id,
            cycle_id=cycle.id,
            status=smart.status,
            source=smart.source[:64],
            smart_wallets=smart.smart_wallets,
            renowned_wallets=smart.renowned_wallets,
            sniper_wallets=smart.sniper_wallets,
            detail=" ".join(smart.warnings)[:4000] or smart.source,
        )
    )
    whales = score.whales
    session.add(
        WhaleEvent(
            token_id=token.id,
            cycle_id=cycle.id,
            status=whales.status,
            source=whales.source[:64],
            whale_wallets=whales.whale_wallets,
            top_10_holder_rate=whales.top_10_holder_rate,
            largest_holder_rate=whales.largest_holder_rate,
            detail=" ".join(whales.warnings)[:4000] or whales.source,
        )
    )
    for candle in analysis.candles:
        session.add(
            TokenCandle(
                token_id=token.id,
                cycle_id=cycle.id,
                resolution=cycle.kline_resolution,
                candle_time=candle.time,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                amount=candle.amount,
            )
        )


def _breakdown(analysis: AnalysisRecord, price_change: Decimal | None) -> dict[str, object]:
    score = analysis.score
    volume_change = None
    for key, value in score.indicators:
        if key in {"volume_acceleration", "amount_acceleration"} and value != "missing":
            volume_change = value
            break
    smart_text = (
        "missing"
        if score.smart_money.smart_wallets is None
        else str(score.smart_money.smart_wallets)
    )
    return {
        "symbol": analysis.symbol,
        "name": analysis.name,
        "price": format_decimal(analysis.price),
        "market_cap": format_decimal(analysis.market_cap),
        "liquidity": format_decimal(analysis.liquidity),
        "volume": format_decimal(analysis.volume),
        "holder_count": analysis.holder_count,
        "creation_timestamp": analysis.creation_timestamp,
        "price_change": format_decimal(price_change),
        "volume_change": volume_change,
        "smart_money": smart_text,
        "entry_consideration": score.entry_consideration,
        "warnings": list(score.warnings),
        "components": [
            [item.name, "unknown" if item.score is None else str(item.score), item.quality]
            for item in score.components
        ],
        "indicators": [list(pair) for pair in score.indicators],
        "smart_money_status": score.smart_money.status,
        "whale_status": score.whales.status,
        "smart_wallets": score.smart_money.smart_wallets,
        "whale_wallets": score.whales.whale_wallets,
        "top_10_holder_rate": format_decimal(score.whales.top_10_holder_rate),
        "largest_holder_rate": format_decimal(score.whales.largest_holder_rate),
        "candles": [
            [
                candle.time,
                format_decimal(candle.open),
                format_decimal(candle.high),
                format_decimal(candle.low),
                format_decimal(candle.close),
            ]
            for candle in analysis.candles
        ],
    }


def _snapshot(session: Session, cycle: RadarCycle) -> CycleSnapshot:
    observations = session.scalars(
        select(TokenObservation).where(TokenObservation.cycle_id == cycle.id)
    ).all()
    analyses = session.scalars(
        select(TokenAnalysis)
        .where(TokenAnalysis.cycle_id == cycle.id)
        .order_by(TokenAnalysis.rank_position)
    ).all()
    watches = session.scalars(select(WatchlistItem).order_by(WatchlistItem.id)).all()
    discoveries: list[DiscoveryRow] = []
    for observation in observations:
        token = session.get(Token, observation.token_id)
        if token is None:
            continue
        discoveries.append(
            DiscoveryRow(
                source=observation.source,
                chain=token.chain,
                address=token.address,
                symbol=token.symbol,
                name=token.name,
                price=format_decimal(observation.price),
                market_cap=format_decimal(observation.market_cap),
                liquidity=format_decimal(observation.liquidity),
                volume=format_decimal(observation.volume),
                holder_count=observation.holder_count,
                creation_timestamp=observation.creation_timestamp,
                route=observation.route,
                price_change=format_decimal(observation.price_change),
            )
        )
    rankings: list[RankRow] = []
    details: list[AnalysisDetail] = []
    for analysis in analyses:
        token = session.get(Token, analysis.token_id)
        if token is None:
            continue
        payload = analysis.breakdown
        rankings.append(_rank_row(token.chain, token.address, analysis, payload))
        details.append(_detail_row(token.chain, token.address, analysis, payload))
    return CycleSnapshot(
        cycle_id=cycle.id,
        status=cycle.status,
        started_at=cycle.started_at.isoformat(),
        finished_at=cycle.finished_at.isoformat(),
        chain=cycle.chain,
        weight_used=cycle.weight_used,
        request_count=cycle.request_count,
        trending_count=cycle.trending_count,
        launch_count=cycle.launch_count,
        analysed_count=cycle.analysed_count,
        note=cycle.note,
        discoveries=tuple(discoveries),
        rankings=tuple(rankings),
        analyses=tuple(details),
        watches=tuple(_watch(item) for item in watches),
    )


def _rank_row(
    chain: str, address: str, analysis: TokenAnalysis, payload: dict[str, object]
) -> RankRow:
    warnings = payload.get("warnings", [])
    return RankRow(
        rank=analysis.rank_position,
        chain=chain,
        address=address,
        symbol=_text(payload.get("symbol")),
        name=_text(payload.get("name")),
        price=_text(payload.get("price")),
        market_cap=_text(payload.get("market_cap")),
        liquidity=_text(payload.get("liquidity")),
        volume=_text(payload.get("volume")),
        holder_count=_int(payload.get("holder_count")),
        creation_timestamp=_int(payload.get("creation_timestamp")),
        price_change=_text(payload.get("price_change")),
        volume_change=_text(payload.get("volume_change")),
        smart_money=str(payload.get("smart_money") or "missing"),
        whale_status=str(payload.get("whale_status") or "missing"),
        security_category=analysis.security_category,
        score=format_decimal(analysis.total_score),
        research_confidence=format_decimal(analysis.confidence),
        entry_consideration=str(payload.get("entry_consideration") or "not_authorized"),
        decision=analysis.decision,
        warnings=tuple(str(item) for item in warnings) if isinstance(warnings, list) else (),
    )


def _detail_row(
    chain: str,
    address: str,
    analysis: TokenAnalysis,
    payload: dict[str, object],
) -> AnalysisDetail:
    warnings = payload.get("warnings", [])
    components = payload.get("components", [])
    indicators = payload.get("indicators", [])
    candles = payload.get("candles", [])
    return AnalysisDetail(
        chain=chain,
        address=address,
        symbol=_text(payload.get("symbol")),
        name=_text(payload.get("name")),
        explanation=analysis.explanation,
        decision=analysis.decision,
        score=format_decimal(analysis.total_score),
        security_category=analysis.security_category,
        liquidity_status=analysis.liquidity_status,
        smart_money_status=str(payload.get("smart_money_status") or "missing"),
        whale_status=str(payload.get("whale_status") or "missing"),
        smart_wallets=_int(payload.get("smart_wallets")),
        whale_wallets=_int(payload.get("whale_wallets")),
        top_10_holder_rate=_text(payload.get("top_10_holder_rate")),
        largest_holder_rate=_text(payload.get("largest_holder_rate")),
        components=_triples(components),
        indicators=_pairs(indicators),
        warnings=tuple(str(item) for item in warnings) if isinstance(warnings, list) else (),
        candles=_candles(candles),
    )


def _token(
    session: Session,
    chain: str,
    address: str,
    symbol: str | None,
    name: str | None,
    seen_at: datetime,
) -> Token:
    token = session.scalar(select(Token).where(Token.chain == chain, Token.address == address))
    if token is None:
        token = Token(
            chain=chain,
            address=address,
            symbol=symbol,
            name=name,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
        session.add(token)
        session.flush()
        return token
    token.last_seen_at = seen_at
    if symbol:
        token.symbol = symbol
    if name:
        token.name = name
    return token


def _upsert_watch(
    session: Session,
    chain: str,
    address: str,
    symbol: str | None,
    note: str,
    source: str,
    *,
    active: bool,
) -> WatchRow:
    item = session.scalar(
        select(WatchlistItem).where(WatchlistItem.chain == chain, WatchlistItem.address == address)
    )
    if item is None:
        item = WatchlistItem(
            chain=chain,
            address=address,
            symbol=symbol,
            note=note[:500],
            source=source[:32],
            active=active,
            added_at=datetime.now(UTC),
        )
        session.add(item)
        session.flush()
    else:
        item.symbol = symbol or item.symbol
        item.note = note[:500]
        item.source = source[:32]
        item.active = active
    return _watch(item)


def _watch(item: WatchlistItem) -> WatchRow:
    return WatchRow(
        chain=item.chain,
        address=item.address,
        symbol=item.symbol,
        note=item.note,
        source=item.source,
        active=item.active,
    )


def _engine(settings: Settings) -> Engine:
    if not settings.database_url:
        raise DatabaseNotConfiguredError(
            "CYVORA_DATABASE_URL is not set. Refusing to assume a database."
        )
    return create_database_engine(settings)


def _text(value: object) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    return None


def _int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def _triples(value: object) -> tuple[tuple[str, str, str], ...]:
    if not isinstance(value, list):
        return ()
    rows: list[tuple[str, str, str]] = []
    for item in value:
        if isinstance(item, list) and len(item) == 3:
            rows.append((str(item[0]), str(item[1]), str(item[2])))
    return tuple(rows)


def _pairs(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        return ()
    rows: list[tuple[str, str]] = []
    for item in value:
        if isinstance(item, list) and len(item) == 2:
            rows.append((str(item[0]), str(item[1])))
    return tuple(rows)


def _candles(
    value: object,
) -> tuple[tuple[int | None, str | None, str | None, str | None, str | None], ...]:
    if not isinstance(value, list):
        return ()
    rows: list[tuple[int | None, str | None, str | None, str | None, str | None]] = []
    for item in value:
        if isinstance(item, list) and len(item) == 5:
            rows.append(
                (_int(item[0]), _text(item[1]), _text(item[2]), _text(item[3]), _text(item[4]))
            )
    return tuple(rows)
