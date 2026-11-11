"""Local supervisor, recovery, backup, and authentication rows.

Live trading and cloud deployment stay false. Wallet reconciliation cannot
be recorded as anything other than not authorized.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class OperationWorker(Base):
    """The latest lifecycle row for one local worker."""

    __tablename__ = "operation_workers"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('radar', 'portfolio', 'freshness', 'notifications')",
            name="ck_operation_workers_kind",
        ),
        CheckConstraint(
            "state IN ('idle', 'running', 'stopped', 'failed')",
            name="ck_operation_workers_state",
        ),
        CheckConstraint(
            "execution_mode IN ('READ_ONLY', 'PAPER')",
            name="ck_operation_workers_mode",
        ),
        CheckConstraint("live_trading_enabled IS false", name="ck_operation_workers_live"),
        CheckConstraint("cloud_deployed IS false", name="ck_operation_workers_cloud"),
    )

    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    restart_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ticks_completed: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cloud_deployed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OperationHeartbeat(Base):
    """One append-only worker observation."""

    __tablename__ = "operation_heartbeats"
    __table_args__ = (
        CheckConstraint(
            "state IN ('idle', 'running', 'stopped', 'failed')",
            name="ck_operation_heartbeats_state",
        ),
        CheckConstraint("live_trading_enabled IS false", name="ck_operation_heartbeats_live"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[str] = mapped_column(String(300), nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class OperationRecovery(Base):
    """One paper-book recovery. The wallet columns cannot say the wallet was read."""

    __tablename__ = "operation_recoveries"
    __table_args__ = (
        CheckConstraint(
            "wallet_reconciliation = 'not_authorized'",
            name="ck_operation_recoveries_wallet",
        ),
        CheckConstraint("wallet_assumed_flat IS false", name="ck_operation_recoveries_flat"),
        CheckConstraint("live_trading_enabled IS false", name="ck_operation_recoveries_live"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    database_state: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_state: Mapped[str] = mapped_column(String(32), nullable=False)
    pending_orders: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_positions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unresolved_orders: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position_status: Mapped[str] = mapped_column(String(32), nullable=False)
    running_strategies: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entries_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    wallet_reconciliation: Mapped[str] = mapped_column(String(32), nullable=False)
    wallet_assumed_flat: Mapped[bool] = mapped_column(Boolean, nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detail: Mapped[str] = mapped_column(String(500), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OperationBackup(Base):
    """A dump attempt. Only the file name is stored, not a database URL."""

    __tablename__ = "operation_backups"
    __table_args__ = (
        CheckConstraint("live_trading_enabled IS false", name="ck_operation_backups_live"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    tool: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(String(300), nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuthEventRow(Base):
    """A local authentication result. There is no token column."""

    __tablename__ = "auth_events"
    __table_args__ = (
        CheckConstraint(
            "result IN ('accepted', 'rejected', 'unconfigured', 'limited')",
            name="ck_auth_events_result",
        ),
        CheckConstraint("live_trading_enabled IS false", name="ck_auth_events_live"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    route_group: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
