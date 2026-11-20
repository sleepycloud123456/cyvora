"""Store dataset quality, collection provenance, and paper strategy audits.

Revision ID: 0009_historical_pipeline
Revises: 0008_readiness
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_historical_pipeline"
down_revision: str | None = "0008_readiness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_index(
        "ix_simulation_bars_dataset_time",
        "simulation_bars",
        ["dataset_id", "observed_at"],
    )
    op.create_table(
        "simulation_collections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(length=48),
            sa.ForeignKey("simulation_datasets.dataset_id"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("detail", sa.String(length=240), nullable=False),
        sa.Column("bar_count", sa.Integer(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_simulation_collections_live"),
    )
    op.create_table(
        "simulation_quality_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(length=48),
            sa.ForeignKey("simulation_datasets.dataset_id"),
            nullable=False,
        ),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bar_count", sa.Integer(), nullable=False),
        sa.Column("mint_count", sa.Integer(), nullable=False),
        sa.Column("gap_count", sa.Integer(), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("outlier_count", sa.Integer(), nullable=False),
        sa.Column("fillable_bar_count", sa.Integer(), nullable=False),
        sa.Column("reserve_bar_count", sa.Integer(), nullable=False),
        sa.Column("depth_bar_count", sa.Integer(), nullable=False),
        sa.Column("volume_only_bar_count", sa.Integer(), nullable=False),
        sa.Column("limitations", _JSON, nullable=False),
        sa.Column("findings", _JSON, nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_simulation_quality_live"),
    )
    op.create_table(
        "paper_strategy_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("strategy_id", sa.String(length=48), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=240), nullable=False),
        sa.Column("signal_strength", sa.String(length=32), nullable=True),
        sa.Column("threshold", sa.String(length=32), nullable=True),
        sa.Column("client_order_id", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_paper_strategy_audits_live"),
        sa.CheckConstraint(
            "action IN ('skipped', 'refused', 'submitted', 'duplicate', 'blocked')",
            name="ck_paper_strategy_audits_action",
        ),
    )


def downgrade() -> None:
    op.drop_table("paper_strategy_audits")
    op.drop_table("simulation_quality_reports")
    op.drop_table("simulation_collections")
    op.drop_index("ix_simulation_bars_dataset_time", table_name="simulation_bars")
