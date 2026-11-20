"""Lifecycle events and notice delivery. Live trading stays unauthorized.

Revision ID: 0013_recovery
Revises: 0012_paper_trader_exited
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_recovery"
down_revision: str | None = "0012_paper_trader_exited"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operation_lifecycle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("component", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.String(length=300), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "component IN ('api', 'supervisor', 'desktop', 'launcher')",
            name="ck_operation_lifecycle_component",
        ),
        sa.CheckConstraint(
            "action IN ('started', 'stopped')",
            name="ck_operation_lifecycle_action",
        ),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_operation_lifecycle_live"),
    )
    op.create_index(
        "ix_operation_lifecycle_occurred",
        "operation_lifecycle",
        ["occurred_at"],
    )
    op.create_table(
        "operation_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dedup_key", sa.String(length=200), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.String(length=300), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "channel IN ('local', 'telegram')",
            name="ck_operation_deliveries_channel",
        ),
        sa.CheckConstraint(
            "status IN ('stored', 'sent', 'failed')",
            name="ck_operation_deliveries_status",
        ),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_operation_deliveries_live"),
        sa.UniqueConstraint("dedup_key", "channel", name="uq_operation_deliveries_notice"),
    )
    op.create_index(
        "ix_operation_deliveries_attempted",
        "operation_deliveries",
        ["channel", "attempted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_operation_deliveries_attempted", table_name="operation_deliveries")
    op.drop_table("operation_deliveries")
    op.drop_index("ix_operation_lifecycle_occurred", table_name="operation_lifecycle")
    op.drop_table("operation_lifecycle")
