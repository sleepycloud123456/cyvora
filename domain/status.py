"""Status values shared by the API, desktop, and database check."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ComponentStatus:
    """One checked dependency."""

    state: str
    detail: str


@dataclass(frozen=True, slots=True)
class StatusSnapshot:
    """Point-in-time foundation status. It never carries market data."""

    app_name: str
    version: str
    phase: str
    environment: str
    execution_mode: str
    live_trading_enabled: bool
    application: ComponentStatus
    database: ComponentStatus
    backend: ComponentStatus
