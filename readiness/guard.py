"""Load the kill switch for the operator paper path. Research ledgers do not call this."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from config.settings import Settings
from domain.status import ComponentStatus

logger = logging.getLogger("cyvora.readiness")

_UNREAD = (
    "The kill switch could not be read. New operator paper orders stay blocked. "
    "Live trading stays locked."
)
_MISSING = (
    "No kill switch row is stored. New operator paper orders stay blocked. "
    "Live trading stays locked."
)
_ENGAGED = (
    "The kill switch is engaged. New operator paper orders are refused. Live trading stays locked."
)
_RELEASED = (
    "The kill switch is released. Shield still evaluates paper orders. Live trading stays locked."
)
_UNCONFIGURED = "The kill switch is not stored. Live trading stays locked."


def operator_orders_blocked(settings: Settings) -> bool:
    """Return whether a new operator paper order must be refused.

    An unconfigured database has no persisted latch, so this returns false and
    the paper gateway's other checks still apply. A configured database that
    cannot be read returns true.
    """

    if not settings.database_url:
        return False
    try:
        from database.repositories.readiness import ReadinessRepository

        return ReadinessRepository(settings).block_new_orders(datetime.now(UTC))
    except Exception as exc:
        logger.warning("kill switch read failed error_type=%s", type(exc).__name__)
        return True


def kill_switch_component(settings: Settings) -> ComponentStatus:
    """Describe the latch for health output. The database URL is not included."""

    if not settings.database_url:
        return ComponentStatus("not_configured", _UNCONFIGURED)
    try:
        from database.repositories.readiness import ReadinessRepository

        engaged = ReadinessRepository(settings).engaged()
    except Exception as exc:
        logger.warning("kill switch status failed error_type=%s", type(exc).__name__)
        return ComponentStatus("unknown", _UNREAD)
    if engaged is None:
        return ComponentStatus("unknown", _MISSING)
    if engaged:
        return ComponentStatus("engaged", _ENGAGED)
    return ComponentStatus("released", _RELEASED)
