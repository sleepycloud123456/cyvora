"""Store the Shield paper risk book.

Revision ID: 0004_shield_risk_engine
Revises: 0003_trading_infrastructure
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_shield_risk_engine"
down_revision: str | None = "0003_trading_infrastructure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MONEY = sa.Numeric(38, 18)
_JSON = postgresql.JSONB(astext_type=sa.Text())
_SHIELD = "shield_decision IN ('not_authorized', 'paper_approved', 'denied')"


def upgrade() -> None:
    op.drop_constraint("ck_trading_orders_shield", "trading_orders", type_="check")
    op.create_check_constraint("ck_trading_orders_shield", "trading_orders", _SHIELD)
    op.create_table(
        "shield_controls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("high_water_equity", _MONEY, nullable=True),
        sa.Column("consecutive_losses", sa.Integer(), nullable=False),
        sa.Column("breach_latched", sa.Boolean(), nullable=False),
        sa.Column("breach_reasons", sa.String(length=300), nullable=False),
        sa.Column("halt_entries", sa.Boolean(), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.Column("limits_json", _JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_shield_controls_singleton"),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_shield_controls_live"),
    )
    op.create_table(
        "shield_daily",
        sa.Column("session_date", sa.Date(), primary_key=True),
        sa.Column("equity_at_open", _MONEY, nullable=False),
        sa.Column("last_equity", _MONEY, nullable=False),
        sa.Column("breached", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "shield_campaigns",
        sa.Column("campaign_id", sa.String(length=80), primary_key=True),
        sa.Column("mint", sa.String(length=64), nullable=False),
        sa.Column("strategy_id", sa.String(length=48), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quantity_opened", _MONEY, nullable=False),
        sa.Column("quantity_closed", _MONEY, nullable=False),
        sa.Column("net_pnl_quote", _MONEY, nullable=False),
        sa.Column("closing_order_id", sa.String(length=80), nullable=True),
        sa.Column("reconciliation", sa.String(length=16), nullable=True),
        sa.Column("creator", sa.String(length=48), nullable=True),
        sa.Column("narrative", sa.String(length=48), nullable=True),
        sa.Column("liquidity_provider", sa.String(length=48), nullable=True),
        sa.Column("driver", sa.String(length=48), nullable=True),
        sa.Column("security", sa.String(length=16), nullable=False),
    )
    op.create_table(
        "shield_stops",
        sa.Column("mint", sa.String(length=64), primary_key=True),
        sa.Column("entry_price", _MONEY, nullable=False),
        sa.Column("stop_price", _MONEY, nullable=False),
        sa.Column("peak_price", _MONEY, nullable=False),
        sa.Column("average_price", _MONEY, nullable=False),
        sa.Column("quantity", _MONEY, nullable=False),
        sa.Column("trailing_active", sa.Boolean(), nullable=False),
        sa.Column("last_trail_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("levels_json", _JSON, nullable=False),
        sa.Column("volatility_used", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "shield_emergencies",
        sa.Column("mint", sa.String(length=64), primary_key=True),
        sa.Column("triggers", sa.String(length=300), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "shield_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_order_id", sa.String(length=80), nullable=True),
        sa.Column("mint", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("requested_quantity", _MONEY, nullable=False),
        sa.Column("allowed_quantity", _MONEY, nullable=True),
        sa.Column("exit_kind", sa.String(length=16), nullable=True),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.String(length=300), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_shield_decisions_live"),
        sa.CheckConstraint(
            "decision IN ('paper_approved', 'denied')",
            name="ck_shield_decisions_paper",
        ),
    )
    op.create_table(
        "shield_notices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("shield_notices")
    op.drop_table("shield_decisions")
    op.drop_table("shield_emergencies")
    op.drop_table("shield_stops")
    op.drop_table("shield_campaigns")
    op.drop_table("shield_daily")
    op.drop_table("shield_controls")
    op.drop_constraint("ck_trading_orders_shield", "trading_orders", type_="check")
    op.create_check_constraint(
        "ck_trading_orders_shield",
        "trading_orders",
        "shield_decision = 'not_authorized'",
    )
