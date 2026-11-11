"""Format stored radar rows for the terminal and the API."""

from __future__ import annotations

from decimal import Decimal

from intelligence.numbers import format_decimal
from intelligence.store import (
    AnalysisDetail,
    AnalysisRecord,
    CycleSnapshot,
    DiscoveryRecord,
    DiscoveryRow,
    RankRow,
    StoredCycle,
    WatchRow,
)


def present_cycle(
    cycle_id: int,
    cycle: StoredCycle,
    watches: tuple[WatchRow, ...],
) -> CycleSnapshot:
    """Build the public snapshot from one stored cycle."""

    changes = {(row.chain, row.address): row.price_change for row in cycle.discoveries}
    return CycleSnapshot(
        cycle_id=cycle_id,
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
        discoveries=tuple(_discovery(row) for row in cycle.discoveries),
        rankings=tuple(_rank(row, changes.get((row.chain, row.address))) for row in cycle.analyses),
        analyses=tuple(_detail(row) for row in cycle.analyses),
        watches=watches,
    )


def _discovery(row: DiscoveryRecord) -> DiscoveryRow:
    return DiscoveryRow(
        source=row.source,
        chain=row.chain,
        address=row.address,
        symbol=row.symbol,
        name=row.name,
        price=format_decimal(row.price),
        market_cap=format_decimal(row.market_cap),
        liquidity=format_decimal(row.liquidity),
        volume=format_decimal(row.volume),
        holder_count=row.holder_count,
        creation_timestamp=row.creation_timestamp,
        route=row.route,
        price_change=format_decimal(row.price_change),
    )


def _rank(row: AnalysisRecord, price_change: object) -> RankRow:
    volume_change = _indicator(row, "volume_acceleration")
    if volume_change is None or volume_change == "missing":
        volume_change = _indicator(row, "amount_acceleration")
    smart = row.score.smart_money
    smart_text = "missing" if smart.smart_wallets is None else str(smart.smart_wallets)
    return RankRow(
        rank=row.rank,
        chain=row.chain,
        address=row.address,
        symbol=row.symbol,
        name=row.name,
        price=format_decimal(row.price),
        market_cap=format_decimal(row.market_cap),
        liquidity=format_decimal(row.liquidity),
        volume=format_decimal(row.volume),
        holder_count=row.holder_count,
        creation_timestamp=row.creation_timestamp,
        price_change=format_decimal(price_change) if isinstance(price_change, Decimal) else None,
        volume_change=None if volume_change in {None, "missing"} else volume_change,
        smart_money=smart_text,
        whale_status=row.score.whales.status,
        security_category=row.score.security.category,
        score=format_decimal(row.score.total),
        research_confidence=format_decimal(row.score.research_confidence),
        entry_consideration=row.score.entry_consideration,
        decision=row.score.decision,
        warnings=row.score.warnings,
    )


def _detail(row: AnalysisRecord) -> AnalysisDetail:
    whales = row.score.whales
    return AnalysisDetail(
        chain=row.chain,
        address=row.address,
        symbol=row.symbol,
        name=row.name,
        explanation=row.explanation,
        decision=row.score.decision,
        score=format_decimal(row.score.total),
        security_category=row.score.security.category,
        liquidity_status=row.score.liquidity.status,
        smart_money_status=row.score.smart_money.status,
        whale_status=row.score.whales.status,
        smart_wallets=row.score.smart_money.smart_wallets,
        whale_wallets=whales.whale_wallets,
        top_10_holder_rate=format_decimal(whales.top_10_holder_rate),
        largest_holder_rate=format_decimal(whales.largest_holder_rate),
        components=tuple(
            (item.name, "unknown" if item.score is None else str(item.score), item.quality)
            for item in row.score.components
        ),
        indicators=row.score.indicators,
        warnings=row.score.warnings,
        candles=tuple(
            (
                candle.time,
                format_decimal(candle.open),
                format_decimal(candle.high),
                format_decimal(candle.low),
                format_decimal(candle.close),
            )
            for candle in row.candles
        ),
    )


def _indicator(row: AnalysisRecord, name: str) -> str | None:
    for key, value in row.score.indicators:
        if key == name:
            return value
    return None
