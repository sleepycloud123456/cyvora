"""Worker and stored-cycle status for the health snapshot."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from config.settings import Settings
from domain.status import ComponentStatus

logger = logging.getLogger("cyvora.operations")


def operation_components(
    settings: Settings, *, now: datetime | None = None
) -> tuple[ComponentStatus, ComponentStatus, ComponentStatus, ComponentStatus]:
    """Return worker, market-data, queue, and websocket words.

    The market-data word comes from the newest stored cycle. GMGN is not called.
    """

    moment = now or datetime.now(UTC)
    queue = ComponentStatus(
        "idle",
        "No external queue is configured. Worker ticks run in process.",
    )
    websocket = ComponentStatus(
        "not_configured",
        "No websocket server is configured. The desktop polls loopback health.",
    )
    if not settings.database_url:
        return (
            ComponentStatus("not_configured", "Worker state is not stored."),
            ComponentStatus("not_configured", "Stored market-data freshness was not read."),
            queue,
            websocket,
        )
    try:
        from database.repositories.operations import read_components

        workers, market = read_components(settings, moment, settings.worker_stale_after_seconds)
    except Exception as exc:
        logger.warning("operations status failed error_type=%s", type(exc).__name__)
        unknown = ComponentStatus(
            "unknown",
            "The status read failed. The driver message was withheld.",
        )
        return unknown, unknown, queue, websocket
    return workers, market, queue, websocket
