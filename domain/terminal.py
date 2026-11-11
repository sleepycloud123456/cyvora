"""Terminal read models. These types never authorize a chain transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

AUTHORITY_NOTE = (
    "Global Shield limits remain the only trade-approval authority. "
    "This profile does not change them and cannot enable live trading."
)
ADVISORY_NOTE = "Advisory only. This finding cannot authorize an order."


class NotificationCategory(StrEnum):
    """Events the terminal can record from stored evidence."""

    NEW_TOKEN = "new_token"
    HIGH_SCORE = "high_score"
    TOKEN_REJECTED = "token_rejected"
    SIMULATED_BUY = "simulated_buy"
    SIMULATED_SELL = "simulated_sell"
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    WHALE_SELLING = "whale_selling"
    SMART_MONEY_ACCUMULATION = "smart_money_accumulation"
    SMART_MONEY_EXIT = "smart_money_exit"
    LIQUIDITY_REMOVAL = "liquidity_removal"
    DAILY_LOSS = "daily_loss"
    DRAWDOWN = "drawdown"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    API_DISCONNECTION = "api_disconnection"
    DATABASE_FAILURE = "database_failure"
    NETWORK_FAILURE = "network_failure"
    APPLICATION_STOPPED = "application_stopped"
    EMERGENCY_STOP = "emergency_stop"
    WEEKLY_REPORT = "weekly_report"


CRITICAL_NOTIFICATIONS = frozenset(
    {
        NotificationCategory.EMERGENCY_STOP,
        NotificationCategory.DAILY_LOSS,
        NotificationCategory.DRAWDOWN,
        NotificationCategory.CONSECUTIVE_LOSSES,
        NotificationCategory.DATABASE_FAILURE,
        NotificationCategory.API_DISCONNECTION,
        NotificationCategory.LIQUIDITY_REMOVAL,
    }
)

UNSOURCED_NOTIFICATIONS = frozenset(
    {
        NotificationCategory.SMART_MONEY_ACCUMULATION,
        NotificationCategory.APPLICATION_STOPPED,
    }
)


@dataclass(frozen=True)
class TradingProfile:
    """A named paper profile. It is not a second risk engine."""

    profile_id: str
    name: str
    strategy_ids: tuple[str, ...]
    signal_threshold: str | None
    active: bool
    live_trading_enabled: bool
    authority_note: str


@dataclass(frozen=True)
class NotificationPreferences:
    """Local delivery rules. Telegram stays off because no bot token is loaded."""

    enabled_categories: tuple[str, ...]
    quiet_start_minute: int | None
    quiet_end_minute: int | None
    minimum_repeat_seconds: int
    telegram_delivery: bool
    live_trading_enabled: bool


@dataclass(frozen=True)
class NotificationRecord:
    """One stored desktop notice. It is not a sent Telegram message."""

    dedup_key: str
    category: str
    subject: str
    detail: str
    evidence_at: datetime
    recorded_at: datetime
    withheld: bool
    delivered_telegram: bool


@dataclass(frozen=True)
class NotificationDraft:
    """A notice ready to insert when its dedup key is new."""

    dedup_key: str
    category: str
    subject: str
    detail: str
    evidence_at: datetime
    withheld: bool


@dataclass(frozen=True)
class RecentOrder:
    """A short paper-order line for the dashboard."""

    client_order_id: str
    symbol: str
    side: str
    state: str
    shield_decision: str
    updated_at: datetime


@dataclass(frozen=True)
class PositionLine:
    """One open paper position joined to stored marks and the Shield plan."""

    mint: str
    symbol: str
    quantity: Decimal
    entry_price: Decimal | None
    current_price: Decimal | None
    price_source: str | None
    price_observed_at: str | None
    position_value: Decimal | None
    unrealized_pnl: Decimal | None
    stop_price: Decimal | None
    trailing_active: bool | None
    take_profits: str
    holding_seconds: int | None
    strategy_id: str | None
    risk_level: str
    quote_symbol: str


@dataclass(frozen=True)
class PortfolioView:
    """Paper figures. A missing figure stays missing."""

    verified_equity: Decimal | None
    verified_equity_detail: str
    sol_balance_detail: str
    usd_detail: str
    allocated: Decimal | None
    allocated_unit: str | None
    allocated_detail: str
    available: Decimal | None
    available_detail: str
    open_positions: int
    unrealized: Decimal | None
    unrealized_detail: str
    realized: Decimal | None
    realized_unit: str | None
    realized_detail: str
    daily_pnl: Decimal | None
    daily_pnl_detail: str
    total_pnl: Decimal | None
    total_pnl_detail: str
    win_rate: Decimal | None
    win_rate_detail: str
    average_profit: Decimal | None
    average_profit_detail: str
    active_strategies: int
    market_condition: str
    market_detail: str
    risk_status: str
    risk_detail: str
    exposure: Decimal | None
    exposure_detail: str
    max_drawdown: Decimal | None
    drawdown_detail: str
    sol_reserve_fraction: Decimal
    sol_reserve_detail: str
    recent: tuple[RecentOrder, ...]
    positions: tuple[PositionLine, ...]


@dataclass(frozen=True)
class StrategyPerformance:
    """Closed paper campaigns for one strategy. Drawdown is not invented per strategy."""

    strategy_id: str
    closed_trades: int
    net_pnl: Decimal
    win_rate: Decimal | None
    profit_factor: Decimal | None


@dataclass(frozen=True)
class TokenPerformance:
    """Closed paper campaigns for one mint."""

    mint: str
    net_pnl: Decimal
    trades: int


@dataclass(frozen=True)
class ResearchComparison:
    """One stored simulation row. It is a separate book and is not deployed."""

    run_id: str
    kind: str
    strategy_id: str
    name: str
    net_profit: Decimal | None
    trade_count: int | None
    max_drawdown: Decimal | None
    parameters_deployed: bool


@dataclass(frozen=True)
class DailyPnl:
    """Change between two stored equity baselines."""

    session_date: date
    previous_date: date
    value: Decimal
    detail: str


@dataclass(frozen=True)
class PeriodPnl:
    """Sum of stored daily changes whose later day falls in the period."""

    label: str
    value: Decimal


@dataclass(frozen=True)
class AnalyticsView:
    """Measurements from stored baselines, campaigns, and simulation reports."""

    equity_points: tuple[tuple[date, Decimal], ...]
    drawdown_points: tuple[tuple[date, Decimal], ...]
    daily: tuple[DailyPnl, ...]
    weekly: tuple[PeriodPnl, ...]
    monthly: tuple[PeriodPnl, ...]
    wins: int
    losses: int
    flats: int
    profit_values: tuple[Decimal, ...]
    average_holding_seconds: Decimal | None
    holding_detail: str
    strategies: tuple[StrategyPerformance, ...]
    tokens: tuple[TokenPerformance, ...]
    research: tuple[ResearchComparison, ...]
    sharpe: Decimal | None
    sharpe_reason: str | None
    sortino: Decimal | None
    sortino_reason: str | None
    risk_adjusted: Decimal | None
    net_profit: Decimal | None
    fees: Decimal
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    """One plain-language note tied to stored evidence."""

    topic: str
    summary: str
    evidence: tuple[str, ...]
    observed_at: str | None
    confidence: str | None
    missing: tuple[str, ...]
    authorizes_order: bool


@dataclass(frozen=True)
class AnalystReport:
    """Local explanation of stored rows. No external model is called."""

    provider: str
    advisory: str
    external_model_called: bool
    findings: tuple[Finding, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class SettingsView:
    """Non-secret operating facts. There is no live-trading control."""

    execution_mode: str
    live_trading_enabled: bool
    live_control_present: bool
    manual_override_locked: bool
    paper_orders_allowed: bool
    database_configured: bool
    gmgn_configured: bool
    api_host: str
    api_port: int
    halt_entries: bool
    breach_latched: bool
    telegram_delivery: bool


@dataclass(frozen=True)
class TerminalSnapshot:
    """Everything the completed terminal pages can show."""

    portfolio: PortfolioView
    analytics: AnalyticsView
    analyst: AnalystReport
    notifications: tuple[NotificationRecord, ...]
    pending_notifications: tuple[NotificationDraft, ...]
    preferences: NotificationPreferences
    profiles: tuple[TradingProfile, ...]
    active_profile_id: str | None
    settings: SettingsView
    generated_at: datetime
