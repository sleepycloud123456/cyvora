"""Local authentication failures. The bearer token is never stored."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from domain.operations import AuthEvent

_DETAILS = {
    "accepted": "Local authentication succeeded.",
    "rejected": "Local authentication failed.",
    "unconfigured": "The local API token is not configured.",
    "limited": "Local authentication is temporarily limited.",
}


def open_failure_count(
    events: Sequence[tuple[str, datetime]],
    *,
    now: datetime,
    window_seconds: float,
) -> int:
    """Count rejected checks that a restart should still treat as open.

    An acceptance inside the window clears older rejections. Events outside
    the window are ignored. The token is not an input.
    """

    cutoff = now - timedelta(seconds=window_seconds)
    recent = [(result, moment) for result, moment in events if moment >= cutoff]
    accepted = [moment for result, moment in recent if result == "accepted"]
    floor = max(accepted) if accepted else None
    return sum(
        1 for result, moment in recent if result == "rejected" and (floor is None or moment > floor)
    )


class AuthGate:
    """Count failed bearer checks in this process."""

    def __init__(self, *, limit: int, window_seconds: float = 60.0) -> None:
        self._limit = limit
        self._window = window_seconds
        self._failures: list[float] = []
        self.events: list[AuthEvent] = []

    @property
    def window_seconds(self) -> float:
        return self._window

    def limited(self, now: float) -> bool:
        self._trim(now)
        return len(self._failures) >= self._limit

    def restore_failures(self, count: int, now: float) -> None:
        """Load a persisted failure count into this process window."""

        if count <= 0:
            return
        self._trim(now)
        self._failures.extend([now] * min(count, self._limit))

    def record_failure(self, now: float) -> None:
        self._trim(now)
        self._failures.append(now)

    def record_success(self) -> None:
        self._failures.clear()

    def remember(self, result: str, route_group: str, occurred_at: datetime) -> AuthEvent:
        event = AuthEvent(result, route_group, _DETAILS[result], occurred_at)
        self.events.append(event)
        if len(self.events) > 50:
            self.events = self.events[-50:]
        return event

    def _trim(self, now: float) -> None:
        cutoff = now - self._window
        self._failures = [item for item in self._failures if item >= cutoff]
