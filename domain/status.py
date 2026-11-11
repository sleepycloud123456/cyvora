"""Status values shared by the API, desktop, and database check."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    gmgn: ComponentStatus
    workers: ComponentStatus = field(
        default_factory=lambda: ComponentStatus(
            "not_running",
            "No supervised worker has reported a heartbeat.",
        )
    )
    market_data: ComponentStatus = field(
        default_factory=lambda: ComponentStatus(
            "not_checked",
            "Stored market-data freshness has not been read.",
        )
    )
    queue: ComponentStatus = field(
        default_factory=lambda: ComponentStatus(
            "idle",
            "No external queue is configured.",
        )
    )
    websocket: ComponentStatus = field(
        default_factory=lambda: ComponentStatus(
            "not_configured",
            "No websocket server is configured.",
        )
    )
    kill_switch: ComponentStatus = field(
        default_factory=lambda: ComponentStatus(
            "not_configured",
            "The kill switch has not been read. Live trading stays locked.",
        )
    )
