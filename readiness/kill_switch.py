"""Operator kill switch rules. The confirmation words are interlocks, not secrets."""

from __future__ import annotations

from domain.readiness import ENGAGE_CONFIRMATION, RELEASE_CONFIRMATION


def confirmation_accepted(action: str, confirmation: str) -> bool:
    """Return whether the operator sent the exact confirmation for this action."""

    if action == "engage":
        return confirmation == ENGAGE_CONFIRMATION
    if action == "release":
        return confirmation == RELEASE_CONFIRMATION
    return False


def orders_blocked(engaged: bool | None) -> bool:
    """Block new operator orders unless the latch is explicitly released.

    ``None`` means the row could not be read or does not exist. That is closed,
    so a missing control does not look like permission to trade.
    """

    return engaged is not False
