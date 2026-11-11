"""Bounded local workers. A tick does not submit an order."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from domain.operations import TickResult


class RadarWorker:
    """Record a radar tick. The default tick does not contact GMGN."""

    kind = "radar"

    def __init__(self, cycle: Callable[[datetime], TickResult] | None = None) -> None:
        self._cycle = cycle

    def tick(self, now: datetime) -> TickResult:
        if self._cycle is None:
            return TickResult(
                self.kind,
                "skipped",
                "GMGN was not contacted. A radar cycle runs only when --include-radar is set.",
            )
        return self._cycle(now)


class FreshnessWorker:
    """Read the newest stored cycle time. This does not call GMGN."""

    kind = "freshness"

    def __init__(
        self,
        latest_at: Callable[[], datetime | None],
        *,
        stale_after_seconds: int,
        database_configured: bool,
    ) -> None:
        self._latest_at = latest_at
        self._stale_after_seconds = stale_after_seconds
        self._database_configured = database_configured

    def tick(self, now: datetime) -> TickResult:
        if not self._database_configured:
            return TickResult(
                self.kind,
                "not_configured",
                "No database is configured. Market data was not requested.",
            )
        try:
            latest = self._latest_at()
        except Exception as exc:
            return TickResult(
                self.kind,
                "failed",
                f"Stored cycle time could not be read ({type(exc).__name__}).",
                critical=True,
            )
        if latest is None:
            return TickResult(self.kind, "missing", "No radar cycle is stored.")
        age = (now - latest).total_seconds()
        if age > self._stale_after_seconds:
            return TickResult(
                self.kind,
                "stale",
                "The latest stored cycle is older than the freshness window.",
            )
        return TickResult(
            self.kind,
            "fresh",
            "The latest stored cycle is inside the freshness window.",
        )


class PortfolioWorker:
    """Count stored open paper positions. A missing read is not zero."""

    kind = "portfolio"

    def __init__(
        self,
        open_positions: Callable[[], int | None],
        *,
        database_configured: bool,
    ) -> None:
        self._open_positions = open_positions
        self._database_configured = database_configured

    def tick(self, now: datetime) -> TickResult:
        del now
        if not self._database_configured:
            return TickResult(
                self.kind,
                "not_configured",
                "The paper book was not read. Wallet balances were not read "
                "and were not assumed flat.",
            )
        try:
            count = self._open_positions()
        except Exception as exc:
            return TickResult(
                self.kind,
                "failed",
                "The paper book could not be read "
                f"({type(exc).__name__}). Wallet balances were not assumed flat.",
                critical=True,
            )
        if count is None:
            return TickResult(
                self.kind,
                "missing",
                "Open paper positions are not stored. Wallet balances were not assumed flat.",
            )
        return TickResult(
            self.kind,
            "ok",
            f"Stored open paper positions: {count}. Wallet balances were not read.",
        )


class NotificationWorker:
    """Confirm that delivery stays local. This tick does not send a message."""

    kind = "notifications"

    def __init__(
        self, stored_notices: Callable[[], int | None], *, database_configured: bool
    ) -> None:
        self._stored_notices = stored_notices
        self._database_configured = database_configured

    def tick(self, now: datetime) -> TickResult:
        del now
        if not self._database_configured:
            return TickResult(
                self.kind,
                "not_configured",
                "Notification storage is not configured. Telegram delivery is off.",
            )
        try:
            count = self._stored_notices()
        except Exception as exc:
            return TickResult(
                self.kind,
                "failed",
                f"Stored notices could not be counted ({type(exc).__name__}). "
                "Telegram delivery is off.",
            )
        shown = 0 if count is None else count
        return TickResult(
            self.kind,
            "ok",
            f"Stored local notices: {shown}. Telegram delivery is off.",
        )
