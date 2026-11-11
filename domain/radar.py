"""Shared radar enumerations.

These names are assessment results. They are not orders and they do not
authorize a transaction. Liquidity quality uses the words stored by
``intelligence.liquidity`` (``observed``, ``conflicting``, ``unknown``),
which are data-quality labels rather than a second security gate.
"""

from __future__ import annotations

from enum import StrEnum


class SecurityCategory(StrEnum):
    """Token security result. UNKNOWN is not a passing grade."""

    APPROVED_FOR_FURTHER_ANALYSIS = "APPROVED_FOR_FURTHER_ANALYSIS"
    CAUTION = "CAUTION"
    HIGH_RISK = "HIGH_RISK"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class LifecycleOutcome(StrEnum):
    """Where a scored token stopped. Later phases own entry and exit."""

    WATCH_SUGGESTED = "watch_suggested"
    BLOCKED_UNKNOWN = "blocked_unknown"
    RANKED = "ranked"
    REJECTED = "rejected"
