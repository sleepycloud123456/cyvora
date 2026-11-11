"""PostgreSQL tables for one radar cycle and its history.

Amounts use ``Numeric(38, 18)``. A later cycle inserts new rows. It does not
overwrite an earlier assessment.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base

MONEY = Numeric(38, 18)


class Token(Base):
    """One Solana mint seen by radar."""

    __tablename__ = "tokens"
    __table_args__ = (UniqueConstraint("chain", "address", name="uq_tokens_chain_address"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain: Mapped[str] = mapped_column(String(16), nullable=False)
    address: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(256))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RadarCycle(Base):
    """One discovery and scoring pass."""

    __tablename__ = "radar_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    weight_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_used: Mapped[int] = mapped_column(Integer, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    trending_count: Mapped[int] = mapped_column(Integer, nullable=False)
    launch_count: Mapped[int] = mapped_column(Integer, nullable=False)
    analysed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(String(500))
    kline_resolution: Mapped[str] = mapped_column(String(8), nullable=False)


class TokenObservation(Base):
    """A discovery-list appearance. Each cycle adds rows."""

    __tablename__ = "token_observations"
    __table_args__ = (Index("ix_token_observations_cycle", "cycle_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id"), nullable=False, index=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("radar_cycles.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    route: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(MONEY)
    market_cap: Mapped[Decimal | None] = mapped_column(MONEY)
    liquidity: Mapped[Decimal | None] = mapped_column(MONEY)
    volume: Mapped[Decimal | None] = mapped_column(MONEY)
    holder_count: Mapped[int | None] = mapped_column(Integer)
    creation_timestamp: Mapped[int | None] = mapped_column(BigInteger)
    price_change: Mapped[Decimal | None] = mapped_column(MONEY)


class TokenAnalysis(Base):
    """Scored token for one cycle, including the public breakdown."""

    __tablename__ = "token_analyses"
    __table_args__ = (
        UniqueConstraint("cycle_id", "token_id", name="uq_token_analyses_cycle_token"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id"), nullable=False, index=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("radar_cycles.id"), nullable=False, index=True)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    total_score: Mapped[Decimal | None] = mapped_column(MONEY)
    confidence: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    security_category: Mapped[str] = mapped_column(String(40), nullable=False)
    liquidity_status: Mapped[str] = mapped_column(String(32), nullable=False)
    liquidity: Mapped[Decimal | None] = mapped_column(MONEY)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class TokenCandle(Base):
    """Candles used for the indicators in one analysis."""

    __tablename__ = "token_candles"
    __table_args__ = (Index("ix_token_candles_token_time", "token_id", "candle_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id"), nullable=False)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("radar_cycles.id"), nullable=False, index=True)
    resolution: Mapped[str] = mapped_column(String(8), nullable=False)
    candle_time: Mapped[int | None] = mapped_column(BigInteger)
    open: Mapped[Decimal | None] = mapped_column(MONEY)
    high: Mapped[Decimal | None] = mapped_column(MONEY)
    low: Mapped[Decimal | None] = mapped_column(MONEY)
    close: Mapped[Decimal | None] = mapped_column(MONEY)
    volume: Mapped[Decimal | None] = mapped_column(MONEY)
    amount: Mapped[Decimal | None] = mapped_column(MONEY)


class SecurityAssessmentRow(Base):
    """Security category and evidence for one analysis."""

    __tablename__ = "security_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id"), nullable=False, index=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("radar_cycles.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(MONEY)
    evidence: Mapped[list[list[str]]] = mapped_column(JSONB, nullable=False)
    missing: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class LiquiditySnapshot(Base):
    """Liquidity figure and the lock claim, which is never verified here."""

    __tablename__ = "liquidity_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id"), nullable=False, index=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("radar_cycles.id"), nullable=False, index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    liquidity: Mapped[Decimal | None] = mapped_column(MONEY)
    burn_claim: Mapped[str] = mapped_column(String(32), nullable=False)
    price_impact: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence: Mapped[list[list[str]]] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class IndicatorSignal(Base):
    """One scoring component."""

    __tablename__ = "indicator_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id"), nullable=False, index=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("radar_cycles.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    quality: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(MONEY)
    weight: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)


class SmartMoneyEvent(Base):
    """Tag-count observation. Not a copied trade."""

    __tablename__ = "smart_money_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id"), nullable=False, index=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("radar_cycles.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    smart_wallets: Mapped[int | None] = mapped_column(Integer)
    renowned_wallets: Mapped[int | None] = mapped_column(Integer)
    sniper_wallets: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str] = mapped_column(Text, nullable=False)


class WhaleEvent(Base):
    """Whale tag count or holder concentration from the same read."""

    __tablename__ = "whale_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id"), nullable=False, index=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("radar_cycles.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    whale_wallets: Mapped[int | None] = mapped_column(Integer)
    top_10_holder_rate: Mapped[Decimal | None] = mapped_column(MONEY)
    largest_holder_rate: Mapped[Decimal | None] = mapped_column(MONEY)
    detail: Mapped[str] = mapped_column(Text, nullable=False)


class WatchlistItem(Base):
    """One research watch. Removal marks ``active`` false and keeps the row."""

    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("chain", "address", name="uq_watchlist_items_identity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain: Mapped[str] = mapped_column(String(16), nullable=False)
    address: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class AuditEvent(Base):
    """Radar decision. The detail must not contain a credential."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    detail: Mapped[str] = mapped_column(String(500), nullable=False)
