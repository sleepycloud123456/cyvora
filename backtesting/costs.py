"""Explicit paper fees. A missing schedule does not become a zero fee."""

from __future__ import annotations

from decimal import Decimal

from backtesting.numbers import quantize_up
from domain.exceptions import TradingValidationError
from domain.simulation import FeeSchedule

_MAX_RATE = Decimal("0.05")


def require_schedule(schedule: FeeSchedule) -> FeeSchedule:
    """Reject a schedule that is unnamed, negative, or above the paper cap."""

    name = schedule.name.strip()
    if not name or len(name) > 40 or not name.replace("_", "").isalnum():
        raise TradingValidationError("A fee schedule name must be 1 to 40 letters, digits, or _.")
    if schedule.fixed_quote < 0 or schedule.rate < 0:
        raise TradingValidationError("A paper fee cannot be negative.")
    if schedule.rate > _MAX_RATE:
        raise TradingValidationError("A paper fee rate cannot exceed 0.05.")
    if not schedule.fixed_quote.is_finite() or not schedule.rate.is_finite():
        raise TradingValidationError("A paper fee must be a finite decimal.")
    return FeeSchedule(name, schedule.fixed_quote, schedule.rate)


def fee_quote(schedule: FeeSchedule, notional: Decimal, quote_decimals: int) -> Decimal:
    """Charge the configured fixed amount plus the rate on quote notional."""

    checked = require_schedule(schedule)
    if notional < 0:
        raise TradingValidationError("Fee notional cannot be negative.")
    raw = checked.fixed_quote + (notional * checked.rate)
    return quantize_up(raw, quote_decimals)


def explicit_zero(schedule: FeeSchedule) -> bool:
    """True when the caller configured both components as zero."""

    checked = require_schedule(schedule)
    return checked.fixed_quote == 0 and checked.rate == 0
