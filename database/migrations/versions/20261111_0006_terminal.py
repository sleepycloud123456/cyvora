"""Store terminal profiles and local notifications. Live flags stay false.

Revision ID: 0006_terminal
Revises: 0005_simulation
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_terminal"
down_revision: str | None = "0005_simulation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "terminal_profiles",
        sa.Column("profile_id", sa.String(length=48), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("strategy_ids", _JSON, nullable=False),
        sa.Column("signal_threshold", sa.String(length=32), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.Column("authority_note", sa.String(length=300), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_terminal_profiles_live"),
    )
    op.create_index(
        "uq_terminal_profiles_one_active",
        "terminal_profiles",
        ["active"],
        unique=True,
        postgresql_where=sa.text("active IS true"),
    )
    op.create_table(
        "terminal_notification_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled_categories", _JSON, nullable=False),
        sa.Column("quiet_start_minute", sa.Integer(), nullable=True),
        sa.Column("quiet_end_minute", sa.Integer(), nullable=True),
        sa.Column("minimum_repeat_seconds", sa.Integer(), nullable=False),
        sa.Column("telegram_delivery", sa.Boolean(), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_terminal_preferences_singleton"),
        sa.CheckConstraint("telegram_delivery IS false", name="ck_terminal_preferences_telegram"),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_terminal_preferences_live"),
        sa.CheckConstraint(
            "minimum_repeat_seconds BETWEEN 60 AND 86400",
            name="ck_terminal_preferences_repeat",
        ),
        sa.CheckConstraint(
            "(quiet_start_minute IS NULL AND quiet_end_minute IS NULL) OR "
            "(quiet_start_minute BETWEEN 0 AND 1439 AND quiet_end_minute BETWEEN 0 AND 1439)",
            name="ck_terminal_preferences_quiet",
        ),
    )
    op.create_table(
        "terminal_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dedup_key", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("subject", sa.String(length=80), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("evidence_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withheld", sa.Boolean(), nullable=False),
        sa.Column("delivered_telegram", sa.Boolean(), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "delivered_telegram IS false", name="ck_terminal_notifications_telegram"
        ),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_terminal_notifications_live"),
        sa.UniqueConstraint("dedup_key", name="uq_terminal_notifications_dedup"),
    )


def downgrade() -> None:
    op.drop_table("terminal_notifications")
    op.drop_table("terminal_notification_preferences")
    op.drop_index("uq_terminal_profiles_one_active", table_name="terminal_profiles")
    op.drop_table("terminal_profiles")
