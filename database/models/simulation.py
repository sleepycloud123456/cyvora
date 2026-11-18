"""Stored historical series, simulation reports, and paper fill assumptions."""

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


class SimulationDataset(Base):
    """One research series. Live trading cannot be enabled on the row."""

    __tablename__ = "simulation_datasets"
    __table_args__ = (
        CheckConstraint("live_trading_enabled IS false", name="ck_simulation_datasets_live"),
    )

    dataset_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    selection_note: Mapped[str] = mapped_column(String(240), nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class SimulationBar(Base):
    """One observation. A missing reserve stays null and is not a zero-impact pool."""

    __tablename__ = "simulation_bars"
    __table_args__ = (
        UniqueConstraint("dataset_id", "mint", "observed_at", name="uq_simulation_bars_point"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("simulation_datasets.dataset_id"), nullable=False
    )
    mint: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal | None] = mapped_column(_MONEY)
    high: Mapped[Decimal | None] = mapped_column(_MONEY)
    low: Mapped[Decimal | None] = mapped_column(_MONEY)
    close: Mapped[Decimal | None] = mapped_column(_MONEY)
    volume_quote: Mapped[Decimal | None] = mapped_column(_MONEY)
    base_volume: Mapped[Decimal | None] = mapped_column(_MONEY)
    base_reserve: Mapped[Decimal | None] = mapped_column(_MONEY)
    quote_reserve: Mapped[Decimal | None] = mapped_column(_MONEY)
    bid: Mapped[Decimal | None] = mapped_column(_MONEY)
    ask: Mapped[Decimal | None] = mapped_column(_MONEY)
    bid_size: Mapped[Decimal | None] = mapped_column(_MONEY)
    ask_size: Mapped[Decimal | None] = mapped_column(_MONEY)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    security: Mapped[str | None] = mapped_column(String(16))
    creator: Mapped[str | None] = mapped_column(String(48))
    volatility: Mapped[Decimal | None] = mapped_column(_MONEY)
    token_age_seconds: Mapped[int | None] = mapped_column(Integer)
    market_condition: Mapped[str | None] = mapped_column(String(16))


class SimulationSignalRow(Base):
    """A signal stored with the series. A backtest cannot read it early."""

    __tablename__ = "simulation_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("simulation_datasets.dataset_id"), nullable=False
    )
    mint: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    name: Mapped[str] = mapped_column(String(16), nullable=False)
    reference: Mapped[str] = mapped_column(String(40), nullable=False)


class SimulationMember(Base):
    """A token the research universe claimed, including tokens with no bars."""

    __tablename__ = "simulation_members"
    __table_args__ = (UniqueConstraint("dataset_id", "mint", name="uq_simulation_members_mint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("simulation_datasets.dataset_id"), nullable=False
    )
    mint: Mapped[str] = mapped_column(String(64), nullable=False)
    included: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)


class SimulationRun(Base):
    """A stored report. Parameters from a run cannot be marked deployed."""

    __tablename__ = "simulation_runs"
    __table_args__ = (
        CheckConstraint("parameters_deployed IS false", name="ck_simulation_runs_deploy"),
        CheckConstraint("live_trading_enabled IS false", name="ck_simulation_runs_live"),
    )

    run_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("simulation_datasets.dataset_id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(48), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    report_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    parameters_deployed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class SimulationCollection(Base):
    """How a dataset was collected. The row cannot enable live trading."""

    __tablename__ = "simulation_collections"
    __table_args__ = (
        CheckConstraint("live_trading_enabled IS false", name="ck_simulation_collections_live"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("simulation_datasets.dataset_id"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[str] = mapped_column(String(240), nullable=False)
    bar_count: Mapped[int] = mapped_column(Integer, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class SimulationQualityReport(Base):
    """Stored quality. Volume-only bars stay not fillable."""

    __tablename__ = "simulation_quality_reports"
    __table_args__ = (
        CheckConstraint("live_trading_enabled IS false", name="ck_simulation_quality_live"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("simulation_datasets.dataset_id"), nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bar_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mint_count: Mapped[int] = mapped_column(Integer, nullable=False)
    gap_count: Mapped[int] = mapped_column(Integer, nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False)
    outlier_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fillable_bar_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reserve_bar_count: Mapped[int] = mapped_column(Integer, nullable=False)
    depth_bar_count: Mapped[int] = mapped_column(Integer, nullable=False)
    volume_only_bar_count: Mapped[int] = mapped_column(Integer, nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    findings: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PaperStrategyAuditRow(Base):
    """One supervised paper evaluation. Live trading stays false."""

    __tablename__ = "paper_strategy_audits"
    __table_args__ = (
        CheckConstraint("live_trading_enabled IS false", name="ck_paper_strategy_audits_live"),
        CheckConstraint(
            "action IN ('skipped', 'refused', 'submitted', 'duplicate', 'blocked')",
            name="ck_paper_strategy_audits_action",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(48), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    signal_strength: Mapped[str | None] = mapped_column(String(32))
    threshold: Mapped[str | None] = mapped_column(String(32))
    client_order_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class SimulationAssumption(Base):
    """The cost model for one paper order. It is not a chain receipt."""

    __tablename__ = "simulation_assumptions"
    __table_args__ = (
        CheckConstraint("simulated IS true", name="ck_simulation_assumptions_simulated"),
        CheckConstraint("live_trading_enabled IS false", name="ck_simulation_assumptions_live"),
    )

    client_order_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    model: Mapped[str] = mapped_column(String(40), nullable=False)
    impact: Mapped[Decimal | None] = mapped_column(_MONEY)
    fee_quote: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    slippage_quote: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
