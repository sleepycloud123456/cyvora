"""Autonomous paper-trader records. Nothing here can enable a live order."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

STRATEGY_ID = "radar-paper"


@dataclass(frozen=True)
class RadarCandidate:
    """One stored radar row the trader may consider. A score is not an order."""

    mint: str
    symbol: str
    score: Decimal | None
    lifecycle: str
    freshness: str
    security_category: str
    price: Decimal | None
    base_reserve: Decimal | None
    quote_reserve: Decimal | None
    creation_timestamp: int | None
    liquidity: Decimal | None = None


@dataclass(frozen=True)
class PoolQuote:
    """A pool read used to price a paper fill. Missing reserves stay missing."""

    mint: str
    price: Decimal | None
    base_reserve: Decimal | None
    quote_reserve: Decimal | None
    observed_at: datetime


@dataclass(frozen=True)
class TraderDecision:
    """Why one candidate or open position was taken, held, or rejected."""

    mint: str
    symbol: str
    action: str
    reason: str
    score: str | None
    client_order_id: str | None
    live_trading_enabled: bool = False


@dataclass(frozen=True)
class TraderTick:
    """One finished pass. The detail is safe to print."""

    status: str
    kill_switch: str
    halt_entries: bool
    entries_blocked: bool
    candidate_count: int
    submitted_count: int
    refused_count: int
    detail: str
    decisions: tuple[TraderDecision, ...]
    equity_quote: Decimal | None
    realized_quote: Decimal | None
    unrealized_quote: Decimal | None
    open_positions: int


@dataclass(frozen=True)
class StoredTraderCycle:
    """The latest stored pass, used by the desktop."""

    status: str
    kill_switch: str
    halt_entries: bool
    entries_blocked: bool
    detail: str
    finished_at: datetime


@dataclass(frozen=True)
class StoredTraderDecision:
    """One stored decision line."""

    symbol: str
    action: str
    reason: str
    score: str | None
    created_at: datetime


@dataclass(frozen=True)
class PaperTraderView:
    """What the dashboard can show. Live trading stays false."""

    status: str
    status_detail: str
    kill_switch: str
    kill_detail: str
    halt_entries: bool
    entries_blocked: bool
    bankroll: Decimal | None
    equity_points: tuple[Decimal, ...]
    decisions: tuple[str, ...]
    observed_at: datetime | None
    live_trading_enabled: bool = False


def unavailable_trader(detail: str) -> PaperTraderView:
    """A view that does not invent a running trader or a balance."""

    return PaperTraderView(
        status="unavailable",
        status_detail=detail,
        kill_switch="unknown",
        kill_detail="The kill switch was not read with this view.",
        halt_entries=False,
        entries_blocked=False,
        bankroll=None,
        equity_points=(),
        decisions=(),
        observed_at=None,
        live_trading_enabled=False,
    )
