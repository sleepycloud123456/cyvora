"""Persisted CYVORA Shield book. Rows describe paper risk, not a wallet."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base

_MONEY = Numeric(38, 18)


class ShieldControl(Base):
    """The single paper risk book. Live trading cannot be enabled from this row."""

    __tablename__ = "shield_controls"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_shield_controls_singleton"),
        CheckConstraint("live_trading_enabled IS false", name="ck_shield_controls_live"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    high_water_equity: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    consecutive_losses: Mapped[int] = mapped_column(Integer, nullable=False)
    breach_latched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    breach_reasons: Mapped[str] = mapped_column(String(300), nullable=False)
    halt_entries: Mapped[bool] = mapped_column(Boolean, nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    limits_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ShieldDaily(Base):
    """One UTC-day equity anchor."""

    __tablename__ = "shield_daily"

    session_date: Mapped[date] = mapped_column(Date, primary_key=True)
    equity_at_open: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    last_equity: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    breached: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ShieldCampaign(Base):
    """One entry-to-flat paper campaign."""

    __tablename__ = "shield_campaigns"

    campaign_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    mint: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(48), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quantity_opened: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    quantity_closed: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    net_pnl_quote: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    closing_order_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reconciliation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    creator: Mapped[str | None] = mapped_column(String(48), nullable=True)
    narrative: Mapped[str | None] = mapped_column(String(48), nullable=True)
    liquidity_provider: Mapped[str | None] = mapped_column(String(48), nullable=True)
    driver: Mapped[str | None] = mapped_column(String(48), nullable=True)
    security: Mapped[str] = mapped_column(String(16), nullable=False)


class ShieldStop(Base):
    """Stop and take-profit plan for one open paper mint."""

    __tablename__ = "shield_stops"

    mint: Mapped[str] = mapped_column(String(64), primary_key=True)
    entry_price: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    stop_price: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    peak_price: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    average_price: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    trailing_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    last_trail_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    levels_json: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)
    volatility_used: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ShieldEmergency(Base):
    """Detected triggers. The row does not create an order."""

    __tablename__ = "shield_emergencies"

    mint: Mapped[str] = mapped_column(String(64), primary_key=True)
    triggers: Mapped[str] = mapped_column(String(300), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ShieldDecision(Base):
    """Audit of one paper decision. The live flag is constrained off."""

    __tablename__ = "shield_decisions"
    __table_args__ = (
        CheckConstraint("live_trading_enabled IS false", name="ck_shield_decisions_live"),
        CheckConstraint(
            "decision IN ('paper_approved', 'denied')",
            name="ck_shield_decisions_paper",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_order_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    mint: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_quantity: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    allowed_quantity: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    exit_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detail: Mapped[str] = mapped_column(String(300), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ShieldNoticeRow(Base):
    """Local breach, emergency, and recovery notes. Nothing is sent off the machine."""

    __tablename__ = "shield_notices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
