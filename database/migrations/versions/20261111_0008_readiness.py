"""Store the operator kill switch. Live trading stays unauthorized.

Revision ID: 0008_readiness
Revises: 0007_operations
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_readiness"
down_revision: str | None = "0007_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "readiness_controls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kill_switch_engaged", sa.Boolean(), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.Column("authorization_state", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_readiness_controls_singleton"),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_readiness_controls_live"),
        sa.CheckConstraint(
            "authorization_state = 'not_authorized'",
            name="ck_readiness_controls_authorization",
        ),
    )
    op.execute(
        "INSERT INTO readiness_controls "
        "(id, kill_switch_engaged, live_trading_enabled, authorization_state, updated_at) "
        "VALUES (1, false, false, 'not_authorized', CURRENT_TIMESTAMP)"
    )
    op.create_table(
        "readiness_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "action IN ('engage', 'release', 'engage_refused', 'release_refused', 'order_refused')",
            name="ck_readiness_events_action",
        ),
        sa.CheckConstraint(
            "result IN ('engaged', 'released', 'refused', 'blocked')",
            name="ck_readiness_events_result",
        ),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_readiness_events_live"),
    )


def downgrade() -> None:
    op.drop_table("readiness_events")
    op.drop_table("readiness_controls")
