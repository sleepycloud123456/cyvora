"""Store local worker, recovery, backup, and authentication rows.

Revision ID: 0007_operations
Revises: 0006_terminal
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_operations"
down_revision: str | None = "0006_terminal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operation_workers",
        sa.Column("kind", sa.String(length=32), primary_key=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restart_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("ticks_completed", sa.Integer(), nullable=False),
        sa.Column("execution_mode", sa.String(length=16), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.Column("cloud_deployed", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('radar', 'portfolio', 'freshness', 'notifications')",
            name="ck_operation_workers_kind",
        ),
        sa.CheckConstraint(
            "state IN ('idle', 'running', 'stopped', 'failed')",
            name="ck_operation_workers_state",
        ),
        sa.CheckConstraint(
            "execution_mode IN ('READ_ONLY', 'PAPER')",
            name="ck_operation_workers_mode",
        ),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_operation_workers_live"),
        sa.CheckConstraint("cloud_deployed IS false", name="ck_operation_workers_cloud"),
    )
    op.create_table(
        "operation_heartbeats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.String(length=300), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "state IN ('idle', 'running', 'stopped', 'failed')",
            name="ck_operation_heartbeats_state",
        ),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_operation_heartbeats_live"),
    )
    op.create_index("ix_operation_heartbeats_kind", "operation_heartbeats", ["kind"])
    op.create_table(
        "operation_recoveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("database_state", sa.String(length=32), nullable=False),
        sa.Column("risk_state", sa.String(length=32), nullable=False),
        sa.Column("pending_orders", sa.Integer(), nullable=True),
        sa.Column("open_positions", sa.Integer(), nullable=True),
        sa.Column("unresolved_orders", sa.Integer(), nullable=True),
        sa.Column("position_status", sa.String(length=32), nullable=False),
        sa.Column("running_strategies", sa.Integer(), nullable=True),
        sa.Column("entries_blocked", sa.Boolean(), nullable=False),
        sa.Column("wallet_reconciliation", sa.String(length=32), nullable=False),
        sa.Column("wallet_assumed_flat", sa.Boolean(), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "wallet_reconciliation = 'not_authorized'",
            name="ck_operation_recoveries_wallet",
        ),
        sa.CheckConstraint("wallet_assumed_flat IS false", name="ck_operation_recoveries_flat"),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_operation_recoveries_live"),
    )
    op.create_table(
        "operation_backups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("tool", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=80), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("detail", sa.String(length=300), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_operation_backups_live"),
    )
    op.create_table(
        "auth_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("route_group", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "result IN ('accepted', 'rejected', 'unconfigured', 'limited')",
            name="ck_auth_events_result",
        ),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_auth_events_live"),
    )


def downgrade() -> None:
    op.drop_table("auth_events")
    op.drop_table("operation_backups")
    op.drop_table("operation_recoveries")
    op.drop_index("ix_operation_heartbeats_kind", table_name="operation_heartbeats")
    op.drop_table("operation_heartbeats")
    op.drop_table("operation_workers")
