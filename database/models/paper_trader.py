"""Stored paper-trader cycles, decisions, and equity points.

A row cannot enable live trading. The paper book itself stays in the
trading tables written by PaperExecutionGateway.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base

_MONEY = Numeric(38, 18)


class PaperTraderCycle(Base):
    """One supervisor pass of the autonomous paper trader."""

    __tablename__ = "paper_trader_cycles"
    __table_args__ = (
        CheckConstraint("live_trading_enabled IS false", name="ck_paper_trader_cycles_live"),
        CheckConstraint(
            "status IN ('running', 'paused', 'blocked', 'skipped', 'failed')",
            name="ck_paper_trader_cycles_status",
        ),
        CheckConstraint(
            "kill_switch IN ('released', 'engaged', 'unreadable', 'not_configured', 'not_checked')",
            name="ck_paper_trader_cycles_kill",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    kill_switch: Mapped[str] = mapped_column(String(16), nullable=False)
    halt_entries: Mapped[bool] = mapped_column(Boolean, nullable=False)
    entries_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_count: Mapped[int] = mapped_column(Integer, nullable=False)
    refused_count: Mapped[int] = mapped_column(Integer, nullable=False)
    detail: Mapped[str] = mapped_column(String(500), nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PaperTraderDecision(Base):
    """Why a candidate or an open position was taken or rejected."""

    __tablename__ = "paper_trader_decisions"
    __table_args__ = (
        CheckConstraint("live_trading_enabled IS false", name="ck_paper_trader_decisions_live"),
        CheckConstraint(
            "action IN ('submitted', 'refused', 'blocked', 'held', 'duplicate', 'skipped')",
            name="ck_paper_trader_decisions_action",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("paper_trader_cycles.id"), nullable=False)
    mint: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    score: Mapped[str | None] = mapped_column(String(32))
    client_order_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PaperTraderEquity(Base):
    """One virtual-bankroll equity point. A missing mark stays null."""

    __tablename__ = "paper_trader_equity"
    __table_args__ = (
        UniqueConstraint("cycle_id", name="uq_paper_trader_equity_cycle"),
        CheckConstraint("live_trading_enabled IS false", name="ck_paper_trader_equity_live"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("paper_trader_cycles.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    equity_quote: Mapped[Decimal | None] = mapped_column(_MONEY)
    realized_quote: Mapped[Decimal | None] = mapped_column(_MONEY)
    unrealized_quote: Mapped[Decimal | None] = mapped_column(_MONEY)
    open_positions: Mapped[int] = mapped_column(Integer, nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
