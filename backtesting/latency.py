"""Execution delay. A fill may use an observation only inside its window."""

from __future__ import annotations

from datetime import datetime, timedelta

from domain.exceptions import TradingValidationError
from domain.simulation import LatencyModel

_MAX_DELAY = 3600
_MAX_AGE = 3600


def require_latency(model: LatencyModel) -> LatencyModel:
    if isinstance(model.delay_seconds, bool) or not isinstance(model.delay_seconds, int):
        raise TradingValidationError("Execution delay must be a whole number of seconds.")
    if isinstance(model.max_quote_age_seconds, bool) or not isinstance(
        model.max_quote_age_seconds, int
    ):
        raise TradingValidationError("Quote age must be a whole number of seconds.")
    if model.delay_seconds < 0 or model.delay_seconds > _MAX_DELAY:
        raise TradingValidationError("Execution delay must be from 0 through 3600 seconds.")
    if model.max_quote_age_seconds < 1 or model.max_quote_age_seconds > _MAX_AGE:
        raise TradingValidationError("Quote age must be from 1 through 3600 seconds.")
    return model


def fill_window(decision_time: datetime, model: LatencyModel) -> tuple[datetime, datetime]:
    """Return the first and last timestamps that may price this decision."""

    checked = require_latency(model)
    start = decision_time + timedelta(seconds=checked.delay_seconds)
    end = start + timedelta(seconds=checked.max_quote_age_seconds)
    return start, end


def inside_window(observed_at: datetime, start: datetime, end: datetime) -> bool:
    return start <= observed_at <= end
