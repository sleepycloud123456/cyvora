"""Build the default local workers. Radar stays offline unless requested."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from config.settings import Settings
from domain.operations import TickResult
from operations.workers import FreshnessWorker, NotificationWorker, PortfolioWorker, RadarWorker


def default_workers(
    settings: Settings, *, allow_radar_network: bool
) -> tuple[RadarWorker, FreshnessWorker, PortfolioWorker, NotificationWorker]:
    cycle = _radar_cycle(settings) if allow_radar_network else None
    configured = bool(settings.database_url)
    return (
        RadarWorker(cycle),
        FreshnessWorker(
            lambda: _latest_cycle(settings),
            stale_after_seconds=settings.worker_stale_after_seconds,
            database_configured=configured,
        ),
        PortfolioWorker(lambda: _open_positions(settings), database_configured=configured),
        NotificationWorker(lambda: _notice_count(settings), database_configured=configured),
    )


def _radar_cycle(settings: Settings) -> Callable[[datetime], TickResult]:
    def run(now: datetime) -> TickResult:
        if settings.gmgn_api_key is None or not settings.database_url:
            return TickResult(
                "radar",
                "skipped",
                "Radar needs a configured key and database. GMGN was not contacted.",
            )
        try:
            from database.repositories.radar import PostgresRadarRepository
            from intelligence.cycle import run_radar_cycle

            result = asyncio.run(
                run_radar_cycle(settings, PostgresRadarRepository(settings), now=now)
            )
        except Exception as exc:
            return TickResult(
                "radar",
                "failed",
                f"The radar cycle failed with {type(exc).__name__}. Trade routes were not called.",
            )
        status = "ok" if result.error_code is None else "failed"
        return TickResult(
            "radar",
            status,
            (f"status={result.status} weight_used={result.weight_used} entry=not_authorized"),
        )

    return run


def _latest_cycle(settings: Settings) -> datetime | None:
    from sqlalchemy import text

    from database.connection import create_database_engine

    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            latest = connection.execute(text("SELECT max(finished_at) FROM radar_cycles")).scalar()
    finally:
        engine.dispose()
    if not isinstance(latest, datetime):
        return None
    if latest.tzinfo is None:
        return latest.replace(tzinfo=UTC)
    return latest


def _open_positions(settings: Settings) -> int:
    from sqlalchemy import text

    from database.connection import create_database_engine

    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            count = connection.execute(
                text("SELECT count(*) FROM trading_positions WHERE quantity <> 0")
            ).scalar_one()
    finally:
        engine.dispose()
    return int(count)


def _notice_count(settings: Settings) -> int:
    from sqlalchemy import text

    from database.connection import create_database_engine

    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            count = connection.execute(
                text("SELECT count(*) FROM terminal_notifications")
            ).scalar_one()
    finally:
        engine.dispose()
    return int(count)
