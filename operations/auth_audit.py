"""Local authentication failures. The bearer token is never stored."""

from __future__ import annotations

from datetime import datetime

from domain.operations import AuthEvent

_DETAILS = {
    "accepted": "Local authentication succeeded.",
    "rejected": "Local authentication failed.",
    "unconfigured": "The local API token is not configured.",
    "limited": "Local authentication is temporarily limited.",
}


class AuthGate:
    """Count failed bearer checks in this process."""

    def __init__(self, *, limit: int, window_seconds: float = 60.0) -> None:
        self._limit = limit
        self._window = window_seconds
        self._failures: list[float] = []
        self.events: list[AuthEvent] = []

    def limited(self, now: float) -> bool:
        self._trim(now)
        return len(self._failures) >= self._limit

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
