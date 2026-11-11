"""Paper-trading records. These types never authorize a chain transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class OrderSide(StrEnum):
    """A simulated buy or sell of a token against a quote currency."""

    BUY = "BUY"
    SELL = "SELL"


class OrderState(StrEnum):
    """Local order lifecycle.

    ``SUBMISSION_PENDING``, ``SUBMITTED``, and ``CONFIRMATION_PENDING`` name
    the chain states from the master spec. Paper execution is not allowed to
    enter them. A paper confirmation is a simulator result, not a Solana
    confirmation.
    """

    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    SIMULATION_PENDING = "SIMULATION_PENDING"
    SIMULATION_PASSED = "SIMULATION_PASSED"
    SUBMISSION_PENDING = "SUBMISSION_PENDING"
    SUBMITTED = "SUBMITTED"
    CONFIRMATION_PENDING = "CONFIRMATION_PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


LIVE_ORDER_STATES = frozenset(
    {
        OrderState.SUBMISSION_PENDING,
        OrderState.SUBMITTED,
        OrderState.CONFIRMATION_PENDING,
    }
)


class SimulationOutcome(StrEnum):
    """Caller-selected paper result. This is not a market or pool model."""

    FILL = "FILL"
    PARTIAL = "PARTIAL"
    REJECT = "REJECT"
    FAIL = "FAIL"


class StrategyState(StrEnum):
    """Lifecycle of a registered strategy. Registration does not start it."""

    REGISTERED = "REGISTERED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    FAULTED = "FAULTED"


class ReconciliationStatus(StrEnum):
    """Comparison of a stored order with a supplied execution report."""

    MATCHED = "MATCHED"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


SHIELD_NOT_AUTHORIZED = "not_authorized"


@dataclass(frozen=True)
class SolanaInstrument:
    """Identity and precision for one Solana mint. The mint is the identity."""

    mint: str
    symbol: str
    size_decimals: int
    price_decimals: int
    quote_symbol: str
    quote_decimals: int


@dataclass(frozen=True)
class MarketQuote:
    """One market observation. Missing prices stay missing."""

    mint: str
    observed_at: datetime
    source: str
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None
    last_price: Decimal | None = None
    last_size: Decimal | None = None
    volume: Decimal | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    size_is_base: bool = False
    bar_resolution: str | None = None


@dataclass(frozen=True)
class OrderEventRecord:
    """One state transition. The note names the internal event."""

    state: OrderState
    note: str
    recorded_at: datetime


@dataclass(frozen=True)
class OrderRecord:
    """A stored paper order. ``simulated`` is always true."""

    client_order_id: str
    idempotency_key: str
    strategy_id: str
    mint: str
    symbol: str
    side: OrderSide
    state: OrderState
    quantity: Decimal
    filled_quantity: Decimal
    reference_price: Decimal
    fill_price: Decimal | None
    fee_quote: Decimal
    slippage_quote: Decimal
    quote_symbol: str
    size_decimals: int
    price_decimals: int
    quote_decimals: int
    outcome: SimulationOutcome
    shield_decision: str
    simulated: bool
    reason: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PositionRecord:
    """Net paper position for one mint. Quantity is base tokens."""

    mint: str
    quantity: Decimal
    average_price: Decimal | None
    cost_quote: Decimal
    realized_pnl_quote: Decimal
    quote_symbol: str
    updated_at: datetime


@dataclass(frozen=True)
class StrategyRecord:
    """A named strategy slot. Parameters are plain strings, never secrets."""

    strategy_id: str
    name: str
    state: StrategyState
    parameters: tuple[tuple[str, str], ...]
    registered_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ReconciliationRecord:
    """The result of comparing one order with a report."""

    client_order_id: str
    status: ReconciliationStatus
    detail: str
    recorded_at: datetime


@dataclass(frozen=True)
class ExecutionReport:
    """A report supplied by the caller. Paper mode has no chain report."""

    client_order_id: str
    state: OrderState
    filled_quantity: Decimal
    fill_price: Decimal | None


@dataclass(frozen=True)
class TradingSnapshot:
    """Rows the terminal can show. An empty snapshot is not sample data."""

    orders: tuple[OrderRecord, ...]
    positions: tuple[PositionRecord, ...]
    strategies: tuple[StrategyRecord, ...]
