"""Store paper-trader cycles, decisions, and virtual equity points.

Revision ID: 0010_paper_trader
Revises: 0009_historical_pipeline
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_paper_trader"
down_revision: str | None = "0009_historical_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MONEY = sa.Numeric(38, 18)


def upgrade() -> None:
    op.create_table(
        "paper_trader_cycles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("kill_switch", sa.String(length=16), nullable=False),
        sa.Column("halt_entries", sa.Boolean(), nullable=False),
        sa.Column("entries_blocked", sa.Boolean(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("submitted_count", sa.Integer(), nullable=False),
        sa.Column("refused_count", sa.Integer(), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_paper_trader_cycles_live"),
        sa.CheckConstraint(
            "status IN ('running', 'paused', 'blocked', 'skipped', 'failed')",
            name="ck_paper_trader_cycles_status",
        ),
        sa.CheckConstraint(
            "kill_switch IN ('released', 'engaged', 'unreadable', 'not_configured', 'not_checked')",
            name="ck_paper_trader_cycles_kill",
        ),
    )
    op.create_table(
        "paper_trader_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cycle_id",
            sa.Integer(),
            sa.ForeignKey("paper_trader_cycles.id"),
            nullable=False,
        ),
        sa.Column("mint", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=240), nullable=False),
        sa.Column("score", sa.String(length=32), nullable=True),
        sa.Column("client_order_id", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_paper_trader_decisions_live"),
        sa.CheckConstraint(
            "action IN ('submitted', 'refused', 'blocked', 'held', 'duplicate', 'skipped')",
            name="ck_paper_trader_decisions_action",
        ),
    )
    op.create_table(
        "paper_trader_equity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cycle_id",
            sa.Integer(),
            sa.ForeignKey("paper_trader_cycles.id"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("equity_quote", _MONEY, nullable=True),
        sa.Column("realized_quote", _MONEY, nullable=True),
        sa.Column("unrealized_quote", _MONEY, nullable=True),
        sa.Column("open_positions", sa.Integer(), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("cycle_id", name="uq_paper_trader_equity_cycle"),
        sa.CheckConstraint("live_trading_enabled IS false", name="ck_paper_trader_equity_live"),
    )


def downgrade() -> None:
    op.drop_table("paper_trader_equity")
    op.drop_table("paper_trader_decisions")
    op.drop_table("paper_trader_cycles")
