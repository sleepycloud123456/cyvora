"""Operator profile, notification, and preference rows. Live flags stay false."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class TerminalProfile(Base):
    """A named paper profile. It cannot change Shield limits or enable live trading."""

    __tablename__ = "terminal_profiles"
    __table_args__ = (
        CheckConstraint("live_trading_enabled IS false", name="ck_terminal_profiles_live"),
        Index(
            "uq_terminal_profiles_one_active",
            "active",
            unique=True,
            postgresql_where=text("active IS true"),
        ),
    )

    profile_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    signal_threshold: Mapped[str | None] = mapped_column(String(32), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    authority_note: Mapped[str] = mapped_column(String(300), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TerminalPreference(Base):
    """Singleton notification rules. Telegram delivery cannot be turned on."""

    __tablename__ = "terminal_notification_preferences"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_terminal_preferences_singleton"),
        CheckConstraint("telegram_delivery IS false", name="ck_terminal_preferences_telegram"),
        CheckConstraint("live_trading_enabled IS false", name="ck_terminal_preferences_live"),
        CheckConstraint(
            "minimum_repeat_seconds BETWEEN 60 AND 86400",
            name="ck_terminal_preferences_repeat",
        ),
        CheckConstraint(
            "(quiet_start_minute IS NULL AND quiet_end_minute IS NULL) OR "
            "(quiet_start_minute BETWEEN 0 AND 1439 AND quiet_end_minute BETWEEN 0 AND 1439)",
            name="ck_terminal_preferences_quiet",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled_categories: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    quiet_start_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quiet_end_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minimum_repeat_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    telegram_delivery: Mapped[bool] = mapped_column(Boolean, nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TerminalNotification(Base):
    """A local notice. Telegram delivery is constrained off."""

    __tablename__ = "terminal_notifications"
    __table_args__ = (
        CheckConstraint("delivered_telegram IS false", name="ck_terminal_notifications_telegram"),
        CheckConstraint("live_trading_enabled IS false", name="ck_terminal_notifications_live"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str] = mapped_column(String(80), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    withheld: Mapped[bool] = mapped_column(Boolean, nullable=False)
    delivered_telegram: Mapped[bool] = mapped_column(Boolean, nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
