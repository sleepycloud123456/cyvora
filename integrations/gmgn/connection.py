"""In-process record of the latest GMGN read."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(slots=True)
class GMGNConnectionState:
    """Connection facts that do not include response bodies or credentials."""

    configured: bool
    state: str = "unknown"
    last_method: str | None = None
    last_path: str | None = None
    last_http_status: int | None = None
    last_api_error: str | None = None
    success_count: int = 0
    failure_count: int = 0
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_latency_ms: int | None = None

    def record_success(self, method: str, path: str, http_status: int, latency_ms: int) -> None:
        self.state = "reachable"
        self.last_method = method
        self.last_path = path
        self.last_http_status = http_status
        self.last_api_error = None
        self.success_count += 1
        self.last_success_at = datetime.now(UTC)
        self.last_latency_ms = latency_ms

    def record_failure(
        self,
        method: str,
        path: str,
        *,
        state: str,
        http_status: int | None,
        api_error: str | None,
        latency_ms: int | None,
    ) -> None:
        self.state = state
        self.last_method = method
        self.last_path = path
        self.last_http_status = http_status
        self.last_api_error = api_error
        self.failure_count += 1
        self.last_failure_at = datetime.now(UTC)
        self.last_latency_ms = latency_ms
