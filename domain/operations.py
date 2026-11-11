"""Local operation records. These types do not authorize a chain transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

WALLET_NOT_AUTHORIZED = "not_authorized"
TERMINAL_ORDER_STATES = frozenset({"CONFIRMED", "FAILED", "CANCELLED", "UNKNOWN"})


@dataclass(frozen=True, slots=True)
class TickResult:
    """One finished worker tick. The detail is safe to store and print."""

    kind: str
    status: str
    detail: str
    critical: bool = False


@dataclass(frozen=True, slots=True)
class BookOrder:
    """The paper-order fields recovery compares. Live states are not stored."""

    mint: str
    side: str
    state: str
    filled_quantity: Decimal


@dataclass(frozen=True, slots=True)
class BookPosition:
    """A stored paper quantity. This is not a wallet balance."""

    mint: str
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class BookSnapshot:
    """What recovery could read. Unread counts stay unset."""

    database_state: str
    risk_state: str
    orders: tuple[BookOrder, ...]
    positions: tuple[BookPosition, ...]
    running_strategies: int
    latest_cycle_at: datetime | None


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    """Paper-book recovery. The wallet is never treated as flat."""

    result: str
    database_state: str
    risk_state: str
    pending_orders: int | None
    open_positions: int | None
    unresolved_orders: int | None
    position_status: str
    running_strategies: int | None
    entries_blocked: bool
    wallet_reconciliation: str
    wallet_assumed_flat: bool
    live_trading_enabled: bool
    detail: str
    started_at: datetime
    finished_at: datetime

    def public_mapping(self) -> dict[str, object]:
        return {
            "result": self.result,
            "database_state": self.database_state,
            "risk_state": self.risk_state,
            "pending_orders": self.pending_orders,
            "open_positions": self.open_positions,
            "unresolved_orders": self.unresolved_orders,
            "position_status": self.position_status,
            "running_strategies": self.running_strategies,
            "entries_blocked": self.entries_blocked,
            "wallet_reconciliation": self.wallet_reconciliation,
            "wallet_assumed_flat": self.wallet_assumed_flat,
            "live_trading_enabled": self.live_trading_enabled,
            "detail": self.detail,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class BackupReport:
    """A local dump attempt. The file name has no connection string."""

    status: str
    tool: str
    file_name: str | None
    size_bytes: int | None
    detail: str
    started_at: datetime
    finished_at: datetime
    live_trading_enabled: bool = False

    def public_mapping(self) -> dict[str, object]:
        return {
            "status": self.status,
            "tool": self.tool,
            "file_name": self.file_name,
            "size_bytes": self.size_bytes,
            "detail": self.detail,
            "live_trading_enabled": self.live_trading_enabled,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class AuthEvent:
    """An authentication result. The token is not a field."""

    result: str
    route_group: str
    detail: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class RetentionPlan:
    """What may age out later. This plan does not delete rows."""

    market_data_days: int
    log_days: int
    backup_files_kept: int
    audit_events_deleted: bool
    backtests_deleted: bool
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunReport:
    """A bounded supervisor run. It does not deploy anything."""

    ticks: int
    failures: int
    critical_failure: bool
    results: tuple[TickResult, ...]
    live_trading_enabled: bool = False
    cloud_deployed: bool = False
