"""Persisted kill switch and readiness audit. Live trading cannot be enabled here."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class ReadinessControl(Base):
    """The single operator latch. Authorization cannot be stored as granted."""

    __tablename__ = "readiness_controls"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_readiness_controls_singleton"),
        CheckConstraint("live_trading_enabled IS false", name="ck_readiness_controls_live"),
        CheckConstraint(
            "authorization_state = 'not_authorized'",
            name="ck_readiness_controls_authorization",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kill_switch_engaged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    authorization_state: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReadinessEvent(Base):
    """One kill-switch or refusal event. There is no confirmation-word column."""

    __tablename__ = "readiness_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('engage', 'release', 'engage_refused', 'release_refused', 'order_refused')",
            name="ck_readiness_events_action",
        ),
        CheckConstraint(
            "result IN ('engaged', 'released', 'refused', 'blocked')",
            name="ck_readiness_events_result",
        ),
        CheckConstraint("live_trading_enabled IS false", name="ck_readiness_events_live"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
