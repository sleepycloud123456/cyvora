"""Create radar history tables.

Revision ID: 0002_radar_intelligence
Revises: 0001_application_metadata
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_radar_intelligence"
down_revision: str | None = "0001_application_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MONEY = sa.Numeric(38, 18)
_JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chain", sa.String(length=16), nullable=False),
        sa.Column("address", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("chain", "address", name="uq_tokens_chain_address"),
    )
    op.create_table(
        "radar_cycles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chain", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weight_budget", sa.Integer(), nullable=False),
        sa.Column("weight_used", sa.Integer(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("trending_count", sa.Integer(), nullable=False),
        sa.Column("launch_count", sa.Integer(), nullable=False),
        sa.Column("analysed_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("kline_resolution", sa.String(length=8), nullable=False),
    )
    op.create_table(
        "token_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_id", sa.Integer(), sa.ForeignKey("tokens.id"), nullable=False),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("radar_cycles.id"), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("route", sa.String(length=64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", _MONEY, nullable=True),
        sa.Column("market_cap", _MONEY, nullable=True),
        sa.Column("liquidity", _MONEY, nullable=True),
        sa.Column("volume", _MONEY, nullable=True),
        sa.Column("holder_count", sa.Integer(), nullable=True),
        sa.Column("creation_timestamp", sa.BigInteger(), nullable=True),
        sa.Column("price_change", _MONEY, nullable=True),
    )
    op.create_index("ix_token_observations_token_id", "token_observations", ["token_id"])
    op.create_index("ix_token_observations_cycle", "token_observations", ["cycle_id"])
    op.create_table(
        "token_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_id", sa.Integer(), sa.ForeignKey("tokens.id"), nullable=False),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("radar_cycles.id"), nullable=False),
        sa.Column("rank_position", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("total_score", _MONEY, nullable=True),
        sa.Column("confidence", _MONEY, nullable=False),
        sa.Column("security_category", sa.String(length=40), nullable=False),
        sa.Column("liquidity_status", sa.String(length=32), nullable=False),
        sa.Column("liquidity", _MONEY, nullable=True),
        sa.Column("freshness", sa.String(length=16), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("breakdown", _JSON, nullable=False),
        sa.UniqueConstraint("cycle_id", "token_id", name="uq_token_analyses_cycle_token"),
    )
    op.create_index("ix_token_analyses_token_id", "token_analyses", ["token_id"])
    op.create_index("ix_token_analyses_cycle_id", "token_analyses", ["cycle_id"])
    op.create_table(
        "token_candles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_id", sa.Integer(), sa.ForeignKey("tokens.id"), nullable=False),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("radar_cycles.id"), nullable=False),
        sa.Column("resolution", sa.String(length=8), nullable=False),
        sa.Column("candle_time", sa.BigInteger(), nullable=True),
        sa.Column("open", _MONEY, nullable=True),
        sa.Column("high", _MONEY, nullable=True),
        sa.Column("low", _MONEY, nullable=True),
        sa.Column("close", _MONEY, nullable=True),
        sa.Column("volume", _MONEY, nullable=True),
        sa.Column("amount", _MONEY, nullable=True),
    )
    op.create_index("ix_token_candles_cycle_id", "token_candles", ["cycle_id"])
    op.create_index("ix_token_candles_token_time", "token_candles", ["token_id", "candle_time"])
    op.create_table(
        "security_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_id", sa.Integer(), sa.ForeignKey("tokens.id"), nullable=False),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("radar_cycles.id"), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("score", _MONEY, nullable=True),
        sa.Column("evidence", _JSON, nullable=False),
        sa.Column("missing", _JSON, nullable=False),
        sa.Column("warnings", _JSON, nullable=False),
    )
    op.create_index("ix_security_assessments_token_id", "security_assessments", ["token_id"])
    op.create_index("ix_security_assessments_cycle_id", "security_assessments", ["cycle_id"])
    op.create_table(
        "liquidity_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_id", sa.Integer(), sa.ForeignKey("tokens.id"), nullable=False),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("radar_cycles.id"), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("liquidity", _MONEY, nullable=True),
        sa.Column("burn_claim", sa.String(length=32), nullable=False),
        sa.Column("price_impact", sa.String(length=32), nullable=False),
        sa.Column("evidence", _JSON, nullable=False),
        sa.Column("warnings", _JSON, nullable=False),
    )
    op.create_index("ix_liquidity_snapshots_token_id", "liquidity_snapshots", ["token_id"])
    op.create_index("ix_liquidity_snapshots_cycle_id", "liquidity_snapshots", ["cycle_id"])
    op.create_table(
        "indicator_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_id", sa.Integer(), sa.ForeignKey("tokens.id"), nullable=False),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("radar_cycles.id"), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("quality", sa.String(length=16), nullable=False),
        sa.Column("score", _MONEY, nullable=True),
        sa.Column("weight", _MONEY, nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
    )
    op.create_index("ix_indicator_signals_token_id", "indicator_signals", ["token_id"])
    op.create_index("ix_indicator_signals_cycle_id", "indicator_signals", ["cycle_id"])
    op.create_table(
        "smart_money_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_id", sa.Integer(), sa.ForeignKey("tokens.id"), nullable=False),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("radar_cycles.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("smart_wallets", sa.Integer(), nullable=True),
        sa.Column("renowned_wallets", sa.Integer(), nullable=True),
        sa.Column("sniper_wallets", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False),
    )
    op.create_index("ix_smart_money_events_token_id", "smart_money_events", ["token_id"])
    op.create_index("ix_smart_money_events_cycle_id", "smart_money_events", ["cycle_id"])
    op.create_table(
        "whale_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_id", sa.Integer(), sa.ForeignKey("tokens.id"), nullable=False),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("radar_cycles.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("whale_wallets", sa.Integer(), nullable=True),
        sa.Column("top_10_holder_rate", _MONEY, nullable=True),
        sa.Column("largest_holder_rate", _MONEY, nullable=True),
        sa.Column("detail", sa.Text(), nullable=False),
    )
    op.create_index("ix_whale_events_token_id", "whale_events", ["token_id"])
    op.create_index("ix_whale_events_cycle_id", "whale_events", ["cycle_id"])
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chain", sa.String(length=16), nullable=False),
        sa.Column("address", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("chain", "address", name="uq_watchlist_items_identity"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=160), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=False),
    )


def downgrade() -> None:
    for name in (
        "audit_events",
        "watchlist_items",
        "whale_events",
        "smart_money_events",
        "indicator_signals",
        "liquidity_snapshots",
        "security_assessments",
        "token_candles",
        "token_analyses",
        "token_observations",
        "radar_cycles",
        "tokens",
    ):
        op.drop_table(name)
