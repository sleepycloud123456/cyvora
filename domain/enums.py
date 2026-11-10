"""Shared enumerations."""

from __future__ import annotations

from enum import StrEnum


class ExecutionMode(StrEnum):
    """Operating modes that cannot submit a real transaction.

    Live modes are intentionally absent. Settings rejects those names
    instead of storing them.
    """

    READ_ONLY = "READ_ONLY"
    PAPER = "PAPER"
