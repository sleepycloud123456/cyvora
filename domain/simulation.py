"""Simulation records. These types never authorize a chain transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class FillModel(StrEnum):
    """How a paper fill price was produced. Candle close is not a model."""

    CONSTANT_PRODUCT = "constant_product"
    DISPLAYED_DEPTH = "displayed_depth"


@dataclass(frozen=True)
class FeeSchedule:
    """An explicit paper fee. A missing schedule is not stored as zero."""

    name: str
    fixed_quote: Decimal
    rate: Decimal


@dataclass(frozen=True)
class LatencyModel:
    """Delay before a decision may use a later observation."""

    delay_seconds: int
    max_quote_age_seconds: int


@dataclass(frozen=True)
class HistoricalBar:
    """One stored observation. Missing book and reserve fields stay missing."""

    mint: str
    symbol: str
    observed_at: datetime
    source: str
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume_quote: Decimal | None = None
    base_volume: Decimal | None = None
    base_reserve: Decimal | None = None
    quote_reserve: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None
    security: str | None = None
    creator: str | None = None
    volatility: Decimal | None = None
    token_age_seconds: int | None = None
    market_condition: str | None = None


@dataclass(frozen=True)
class HistoricalSignal:
    """A signal known at ``observed_at``. A later backtest step cannot see it early."""

    mint: str
    observed_at: datetime
    name: str
    reference: str


@dataclass(frozen=True)
class UniverseMember:
    """One token the research universe claimed to include."""

    mint: str
    included: bool
    reason: str


@dataclass(frozen=True)
class HistoricalDataset:
    """Bars and the selection note that explains which tokens were kept."""

    dataset_id: str
    name: str
    source: str
    selection_note: str
    bars: tuple[HistoricalBar, ...]
    signals: tuple[HistoricalSignal, ...]
    members: tuple[UniverseMember, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class FillPlan:
    """A priced paper fill, or a refusal that does not invent a price."""

    priced: bool
    reason: str | None
    model: str | None
    outcome: str | None
    quantity: Decimal | None
    reference_price: Decimal | None
    slippage_quote: Decimal | None
    fee_quote: Decimal | None
    impact: Decimal | None
    liquidity_quote: Decimal | None
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionAssumption:
    """The cost model attached to one simulated order."""

    client_order_id: str
    model: str
    impact: Decimal | None
    fee_quote: Decimal
    slippage_quote: Decimal
    delay_seconds: int
    limitations: tuple[str, ...]
    simulated: bool
    live_trading_enabled: bool


@dataclass(frozen=True)
class OrderSummary:
    """One simulated order inside a report. It is not a chain receipt."""

    client_order_id: str
    strategy_id: str
    mint: str
    side: str
    state: str
    quantity: Decimal
    filled_quantity: Decimal
    fill_price: Decimal | None
    fee_quote: Decimal
    slippage_quote: Decimal
    shield_decision: str
    reason: str | None


@dataclass(frozen=True)
class Refusal:
    """A decision that was not given a fabricated fill."""

    mint: str
    observed_at: datetime
    side: str
    reason: str


@dataclass(frozen=True)
class PerformanceReport:
    """Measured results. Sharpe and Sortino stay empty when the sample is too small."""

    total_return: Decimal | None
    net_profit: Decimal | None
    gross_profit: Decimal
    gross_loss: Decimal
    win_rate: Decimal | None
    average_win: Decimal | None
    average_loss: Decimal | None
    profit_factor: Decimal | None
    max_drawdown: Decimal | None
    sharpe: Decimal | None
    sharpe_reason: str | None
    sortino: Decimal | None
    sortino_reason: str | None
    average_holding_seconds: Decimal | None
    trade_count: int
    order_count: int
    exposure: Decimal | None
    fees: Decimal
    strategy_contribution: tuple[tuple[str, Decimal], ...]
    risk_adjusted: Decimal | None
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class WindowResult:
    """One walk-forward split. The test window did not choose the parameters."""

    train_started_at: datetime
    train_ended_at: datetime
    test_started_at: datetime
    test_ended_at: datetime
    selected_parameters: tuple[tuple[str, str], ...] | None
    train_net_profit: Decimal | None
    test_net_profit: Decimal | None
    test_trade_count: int
    selection_reason: str


@dataclass(frozen=True)
class StrategySummary:
    """One strategy on its own paper book. It is not a combined portfolio."""

    strategy_id: str
    name: str
    net_profit: Decimal | None
    trade_count: int
    max_drawdown: Decimal | None
    parameters: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SimulationReport:
    """A stored simulation. ``parameters_deployed`` is always false."""

    run_id: str
    dataset_id: str
    kind: str
    strategy_id: str
    created_at: datetime
    starting_equity: Decimal
    ending_equity: Decimal | None
    performance: PerformanceReport
    orders: tuple[OrderSummary, ...]
    refusals: tuple[Refusal, ...]
    missing_tokens: tuple[str, ...]
    limitations: tuple[str, ...]
    parameters_deployed: bool
    windows: tuple[WindowResult, ...]
    strategies: tuple[StrategySummary, ...]
