"""CYVORA Shield records. Approval here is paper-only and never a live order."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

PAPER_APPROVED = "paper_approved"
SHIELD_DENIED = "denied"
LEGACY_NOT_AUTHORIZED = "not_authorized"
PAPER_SHIELD_DECISIONS = frozenset({PAPER_APPROVED, SHIELD_DENIED, LEGACY_NOT_AUTHORIZED})
RECOVERY_PHRASE = "RECOVER_PAPER_ENTRIES"
STOP_NOT_GUARANTEED = "Planned stop is not a guaranteed exit."


class ExitKind(StrEnum):
    """Why an order exists. Shield records the kind and does not invent one."""

    ENTRY = "entry"
    NORMAL = "normal"
    SIGNAL = "signal"
    TIME = "time"
    EMERGENCY = "emergency"
    TAKE_PROFIT = "take_profit"


class SecurityPosture(StrEnum):
    """Caller-supplied security posture. Unknown is not treated as clear."""

    CLEAR = "clear"
    UNKNOWN = "unknown"
    RESTRICTED = "restricted"


@dataclass(frozen=True)
class TakeProfitLevel:
    """One configured gain and the fraction of the position planned for it."""

    gain_fraction: Decimal
    quantity_fraction: Decimal


@dataclass(frozen=True)
class TakeProfitSlice:
    """Planned quantity for one level. Consumed quantity never exceeds the plan."""

    gain_fraction: Decimal
    quantity_fraction: Decimal
    planned_quantity: Decimal
    consumed_quantity: Decimal


@dataclass(frozen=True)
class ShieldLimits:
    """Configurable controls. Invalid combinations are rejected before use."""

    max_deployed_fraction: Decimal
    min_sol_reserve_fraction: Decimal
    risk_per_trade_fraction: Decimal
    daily_loss_fraction: Decimal
    max_drawdown_fraction: Decimal
    max_consecutive_losses: int
    max_liquidity_participation: Decimal
    max_cluster_fraction: Decimal
    max_price_impact: Decimal
    volatility_multiplier: Decimal
    liquidity_widen_below: Decimal
    young_token_seconds: int
    young_token_multiplier: Decimal
    stressed_multiplier: Decimal
    trail_distance_fraction: Decimal
    trail_activation_fraction: Decimal
    break_even_fraction: Decimal
    trail_min_interval_seconds: int
    liquidity_removal_ratio: Decimal
    price_collapse_ratio: Decimal
    max_quote_age_seconds: int
    max_valuation_age_seconds: int
    time_exit_seconds: int
    take_profit_levels: tuple[TakeProfitLevel, ...]


@dataclass(frozen=True)
class DailyBaseline:
    """UTC-day equity anchor. A restart reloads this row instead of minting a new one."""

    session_date: date
    equity_at_open: Decimal
    last_equity: Decimal
    breached: bool
    recorded_at: datetime


@dataclass(frozen=True)
class CampaignRecord:
    """One entry-to-flat campaign. Partial exits stay inside the same campaign."""

    campaign_id: str
    mint: str
    strategy_id: str
    opened_at: datetime
    closed_at: datetime | None
    quantity_opened: Decimal
    quantity_closed: Decimal
    net_pnl_quote: Decimal
    closing_order_id: str | None
    reconciliation: str | None
    creator: str | None
    narrative: str | None
    liquidity_provider: str | None
    driver: str | None
    security: str


@dataclass(frozen=True)
class StopPlan:
    """Stop, trail, and take-profit plan for one open paper position."""

    mint: str
    entry_price: Decimal
    stop_price: Decimal
    peak_price: Decimal
    average_price: Decimal
    quantity: Decimal
    trailing_active: bool
    last_trail_at: datetime | None
    levels: tuple[TakeProfitSlice, ...]
    volatility_used: bool


@dataclass(frozen=True)
class EmergencyFlag:
    """A detected emergency. It does not submit an order."""

    mint: str
    triggers: tuple[str, ...]
    recorded_at: datetime
    active: bool


@dataclass(frozen=True)
class ShieldSnapshot:
    """Persisted risk book. The high-water mark and baselines survive a restart."""

    limits: ShieldLimits
    high_water_equity: Decimal | None
    consecutive_losses: int
    breach_latched: bool
    breach_reasons: tuple[str, ...]
    halt_entries: bool
    daily: tuple[DailyBaseline, ...]
    campaigns: tuple[CampaignRecord, ...]
    stops: tuple[StopPlan, ...]
    emergencies: tuple[EmergencyFlag, ...]


@dataclass(frozen=True)
class EmergencyEvidence:
    """Evidence the caller actually has. Missing fields stay missing."""

    previous_liquidity: Decimal | None
    current_liquidity: Decimal | None
    previous_price: Decimal | None
    current_price: Decimal | None
    whale_sell_reported: bool
    whale_source: str | None
    smart_money_exit_reported: bool
    smart_money_source: str | None
    estimated_impact: Decimal | None
    trading_restricted: bool
    restriction_source: str | None
    quote_observed_at: datetime | None


@dataclass(frozen=True)
class RiskIntent:
    """Inputs for one paper decision. None means the caller did not supply that fact."""

    mint: str
    side: str
    quantity: Decimal
    reference_price: Decimal
    fee_quote: Decimal
    slippage_quote: Decimal
    size_decimals: int
    price_decimals: int
    quote_decimals: int
    quote_symbol: str
    stop_price: Decimal | None
    equity_quote: Decimal | None
    sol_balance: Decimal | None
    valued_at: datetime | None
    marks: tuple[tuple[str, Decimal], ...]
    liquidity_quote: Decimal | None
    volatility: Decimal | None
    confidence: Decimal | None
    token_age_seconds: int | None
    market_condition: str | None
    security: str | None
    creator: str | None
    narrative: str | None
    liquidity_provider: str | None
    driver: str | None
    estimated_impact: Decimal | None
    exit_kind: str
    signal_ref: str | None
    emergency: EmergencyEvidence | None


@dataclass(frozen=True)
class ShieldDecisionRecord:
    """One stored decision. ``live_trading_enabled`` is always false."""

    client_order_id: str | None
    mint: str
    side: str
    decision: str
    reason: str | None
    requested_quantity: Decimal
    allowed_quantity: Decimal | None
    exit_kind: str | None
    live_trading_enabled: bool
    detail: str
    recorded_at: datetime


@dataclass(frozen=True)
class ShieldNotice:
    """A local record of a breach, emergency, or recovery. No external notifier is used."""

    kind: str
    detail: str
    recorded_at: datetime


@dataclass(frozen=True)
class Evaluation:
    """The pure result of one decision, including the snapshot a store should keep."""

    snapshot: ShieldSnapshot
    approved: bool
    reason: str | None
    allowed_quantity: Decimal | None
    binding_limit: str | None
    notes: tuple[str, ...]
    effective_stop: Decimal | None
    expected_fill: Decimal | None
    exit_kind: str
    notices: tuple[ShieldNotice, ...]
