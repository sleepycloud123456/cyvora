"""Create paper trading tables.

Revision ID: 0003_trading_infrastructure
Revises: 0002_radar_intelligence
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_trading_infrastructure"
down_revision: str | None = "0002_radar_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MONEY = sa.Numeric(38, 18)
_JSON = postgresql.JSONB(astext_type=sa.Text())
_NO_LIVE = "state NOT IN ('SUBMISSION_PENDING', 'SUBMITTED', 'CONFIRMATION_PENDING')"


def upgrade() -> None:
    op.create_table(
        "trading_instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chain", sa.String(length=16), nullable=False),
        sa.Column("mint", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("size_decimals", sa.Integer(), nullable=False),
        sa.Column("price_decimals", sa.Integer(), nullable=False),
        sa.Column("quote_symbol", sa.String(length=12), nullable=False),
        sa.Column("quote_decimals", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("mint", name="uq_trading_instruments_mint"),
    )
    op.create_table(
        "trading_strategies",
        sa.Column("strategy_id", sa.String(length=48), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("parameters", _JSON, nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "trading_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_order_id", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("strategy_id", sa.String(length=48), nullable=False),
        sa.Column("mint", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("quantity", _MONEY, nullable=False),
        sa.Column("filled_quantity", _MONEY, nullable=False),
        sa.Column("reference_price", _MONEY, nullable=False),
        sa.Column("fill_price", _MONEY, nullable=True),
        sa.Column("fee_quote", _MONEY, nullable=False),
        sa.Column("slippage_quote", _MONEY, nullable=False),
        sa.Column("quote_symbol", sa.String(length=12), nullable=False),
        sa.Column("size_decimals", sa.Integer(), nullable=False),
        sa.Column("price_decimals", sa.Integer(), nullable=False),
        sa.Column("quote_decimals", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("shield_decision", sa.String(length=32), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("execution_mode", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_order_id", name="uq_trading_orders_client_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_trading_orders_idempotency"),
        sa.CheckConstraint("simulated IS true", name="ck_trading_orders_simulated"),
        sa.CheckConstraint(
            "shield_decision = 'not_authorized'",
            name="ck_trading_orders_shield",
        ),
        sa.CheckConstraint("execution_mode = 'PAPER'", name="ck_trading_orders_mode"),
        sa.CheckConstraint(_NO_LIVE, name="ck_trading_orders_no_live_state"),
    )
    op.create_table(
        "trading_order_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("trading_orders.id"), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(_NO_LIVE, name="ck_trading_order_events_no_live_state"),
    )
    op.create_index("ix_trading_order_events_order_id", "trading_order_events", ["order_id"])
    op.create_table(
        "trading_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mint", sa.String(length=64), nullable=False),
        sa.Column("quantity", _MONEY, nullable=False),
        sa.Column("average_price", _MONEY, nullable=True),
        sa.Column("cost_quote", _MONEY, nullable=False),
        sa.Column("realized_pnl_quote", _MONEY, nullable=False),
        sa.Column("quote_symbol", sa.String(length=12), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("mint", name="uq_trading_positions_mint"),
    )
    op.create_table(
        "trading_reconciliations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_order_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.String(length=300), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for name in (
        "trading_reconciliations",
        "trading_positions",
        "trading_order_events",
        "trading_orders",
        "trading_strategies",
        "trading_instruments",
    ):
        op.drop_table(name)
