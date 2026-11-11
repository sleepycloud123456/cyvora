"""Paper order, position, and strategy tables."""

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base

_MONEY = Numeric(38, 18)


class TradingInstrument(Base):
    """One Solana mint the paper ledger has seen."""

    __tablename__ = "trading_instruments"
    __table_args__ = (UniqueConstraint("mint", name="uq_trading_instruments_mint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain: Mapped[str] = mapped_column(String(16), nullable=False)
    mint: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    size_decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    price_decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_symbol: Mapped[str] = mapped_column(String(12), nullable=False)
    quote_decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TradingStrategy(Base):
    """A registered strategy slot. Parameters are plain strings."""

    __tablename__ = "trading_strategies"

    strategy_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    parameters: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TradingOrder(Base):
    """One paper order. Live submission states are rejected by a check constraint."""

    __tablename__ = "trading_orders"
    __table_args__ = (
        UniqueConstraint("client_order_id", name="uq_trading_orders_client_id"),
        UniqueConstraint("idempotency_key", name="uq_trading_orders_idempotency"),
        CheckConstraint("simulated IS true", name="ck_trading_orders_simulated"),
        CheckConstraint(
            "shield_decision = 'not_authorized'",
            name="ck_trading_orders_shield",
        ),
        CheckConstraint("execution_mode = 'PAPER'", name="ck_trading_orders_mode"),
        CheckConstraint(
            "state NOT IN ('SUBMISSION_PENDING', 'SUBMITTED', 'CONFIRMATION_PENDING')",
            name="ck_trading_orders_no_live_state",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(48), nullable=False)
    mint: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    filled_quantity: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    reference_price: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    fill_price: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    fee_quote: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    slippage_quote: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    quote_symbol: Mapped[str] = mapped_column(String(12), nullable=False)
    size_decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    price_decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    shield_decision: Mapped[str] = mapped_column(String(32), nullable=False)
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TradingOrderEvent(Base):
    """One paper state transition."""

    __tablename__ = "trading_order_events"
    __table_args__ = (
        CheckConstraint(
            "state NOT IN ('SUBMISSION_PENDING', 'SUBMITTED', 'CONFIRMATION_PENDING')",
            name="ck_trading_order_events_no_live_state",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("trading_orders.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str] = mapped_column(String(300), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TradingPosition(Base):
    """Net paper position for one mint."""

    __tablename__ = "trading_positions"
    __table_args__ = (UniqueConstraint("mint", name="uq_trading_positions_mint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mint: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    average_price: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    cost_quote: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    realized_pnl_quote: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    quote_symbol: Mapped[str] = mapped_column(String(12), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TradingReconciliation(Base):
    """A stored comparison. It does not submit a replacement order."""

    __tablename__ = "trading_reconciliations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[str] = mapped_column(String(300), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
