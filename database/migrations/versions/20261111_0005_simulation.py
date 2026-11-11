"""Store simulation series and reports. Live flags stay false.

Revision ID: 0005_simulation
Revises: 0004_shield_risk_engine
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_simulation"
down_revision: str | None = "0004_shield_risk_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MONEY = sa.Numeric(38, 18)
_JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "simulation_datasets",
        sa.Column("dataset_id", sa.String(length=48), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("selection_note", sa.String(length=240), nullable=False),
        sa.Column("limitations", _JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_simulation_datasets_live"),
    )
    op.create_table(
        "simulation_bars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(length=48),
            sa.ForeignKey("simulation_datasets.dataset_id"),
            nullable=False,
        ),
        sa.Column("mint", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", _MONEY, nullable=True),
        sa.Column("high", _MONEY, nullable=True),
        sa.Column("low", _MONEY, nullable=True),
        sa.Column("close", _MONEY, nullable=True),
        sa.Column("volume_quote", _MONEY, nullable=True),
        sa.Column("base_volume", _MONEY, nullable=True),
        sa.Column("base_reserve", _MONEY, nullable=True),
        sa.Column("quote_reserve", _MONEY, nullable=True),
        sa.Column("bid", _MONEY, nullable=True),
        sa.Column("ask", _MONEY, nullable=True),
        sa.Column("bid_size", _MONEY, nullable=True),
        sa.Column("ask_size", _MONEY, nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("security", sa.String(length=16), nullable=True),
        sa.Column("creator", sa.String(length=48), nullable=True),
        sa.Column("volatility", _MONEY, nullable=True),
        sa.Column("token_age_seconds", sa.Integer(), nullable=True),
        sa.Column("market_condition", sa.String(length=16), nullable=True),
        sa.UniqueConstraint("dataset_id", "mint", "observed_at", name="uq_simulation_bars_point"),
    )
    op.create_table(
        "simulation_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(length=48),
            sa.ForeignKey("simulation_datasets.dataset_id"),
            nullable=False,
        ),
        sa.Column("mint", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=16), nullable=False),
        sa.Column("reference", sa.String(length=40), nullable=False),
    )
    op.create_table(
        "simulation_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(length=48),
            sa.ForeignKey("simulation_datasets.dataset_id"),
            nullable=False,
        ),
        sa.Column("mint", sa.String(length=64), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=80), nullable=False),
        sa.UniqueConstraint("dataset_id", "mint", name="uq_simulation_members_mint"),
    )
    op.create_table(
        "simulation_runs",
        sa.Column("run_id", sa.String(length=48), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(length=48),
            sa.ForeignKey("simulation_datasets.dataset_id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("strategy_id", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_json", _JSON, nullable=False),
        sa.Column("parameters_deployed", sa.Boolean(), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint("parameters_deployed IS false", name="ck_simulation_runs_deploy"),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_simulation_runs_live"),
    )
    op.create_table(
        "simulation_assumptions",
        sa.Column("client_order_id", sa.String(length=80), primary_key=True),
        sa.Column("model", sa.String(length=40), nullable=False),
        sa.Column("impact", _MONEY, nullable=True),
        sa.Column("fee_quote", _MONEY, nullable=False),
        sa.Column("slippage_quote", _MONEY, nullable=False),
        sa.Column("delay_seconds", sa.Integer(), nullable=False),
        sa.Column("limitations", _JSON, nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint("simulated IS true", name="ck_simulation_assumptions_simulated"),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_simulation_assumptions_live"),
    )


def downgrade() -> None:
    op.drop_table("simulation_assumptions")
    op.drop_table("simulation_runs")
    op.drop_table("simulation_members")
    op.drop_table("simulation_signals")
    op.drop_table("simulation_bars")
    op.drop_table("simulation_datasets")
