"""Records passed between the radar cycle, the database, and the terminal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from intelligence.opportunity import CandlePoint, TokenScore


@dataclass(frozen=True, slots=True)
class DiscoveryRecord:
    """One token row from a discovery route."""

    source: str
    chain: str
    address: str
    symbol: str | None
    name: str | None
    price: Decimal | None
    market_cap: Decimal | None
    liquidity: Decimal | None
    volume: Decimal | None
    holder_count: int | None
    creation_timestamp: int | None
    route: str
    retrieved_at: datetime
    price_change: Decimal | None


@dataclass(frozen=True, slots=True)
class AnalysisRecord:
    """One scored token. Historical rows are inserted, not updated."""

    chain: str
    address: str
    symbol: str | None
    name: str | None
    price: Decimal | None
    market_cap: Decimal | None
    liquidity: Decimal | None
    volume: Decimal | None
    holder_count: int | None
    creation_timestamp: int | None
    sources: tuple[str, ...]
    routes: tuple[str, ...]
    freshness: str
    score: TokenScore
    candles: tuple[CandlePoint, ...]
    explanation: str
    rank: int


@dataclass(frozen=True, slots=True)
class StoredCycle:
    """A finished or failed cycle ready to insert."""

    chain: str
    status: str
    started_at: datetime
    finished_at: datetime
    weight_budget: int
    weight_used: int
    request_count: int
    trending_count: int
    launch_count: int
    analysed_count: int
    error_code: str | None
    note: str | None
    kline_resolution: str
    discoveries: tuple[DiscoveryRecord, ...]
    analyses: tuple[AnalysisRecord, ...]
    watch_suggestions: tuple[tuple[str, str, str | None], ...]


@dataclass(frozen=True, slots=True)
class DiscoveryRow:
    """Public discovery fields for the terminal and the API."""

    source: str
    chain: str
    address: str
    symbol: str | None
    name: str | None
    price: str | None
    market_cap: str | None
    liquidity: str | None
    volume: str | None
    holder_count: int | None
    creation_timestamp: int | None
    route: str
    price_change: str | None


@dataclass(frozen=True, slots=True)
class RankRow:
    """One ranked token. Entry stays not authorized."""

    rank: int
    chain: str
    address: str
    symbol: str | None
    name: str | None
    price: str | None
    market_cap: str | None
    liquidity: str | None
    volume: str | None
    holder_count: int | None
    creation_timestamp: int | None
    price_change: str | None
    volume_change: str | None
    smart_money: str
    whale_status: str
    security_category: str
    score: str | None
    research_confidence: str | None
    entry_consideration: str
    decision: str
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnalysisDetail:
    """Breakdown shown on the token analysis page."""

    chain: str
    address: str
    symbol: str | None
    name: str | None
    explanation: str
    decision: str
    score: str | None
    security_category: str
    liquidity_status: str
    smart_money_status: str
    whale_status: str
    smart_wallets: int | None
    whale_wallets: int | None
    top_10_holder_rate: str | None
    largest_holder_rate: str | None
    components: tuple[tuple[str, str, str], ...]
    indicators: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]
    candles: tuple[tuple[int | None, str | None, str | None, str | None, str | None], ...]


@dataclass(frozen=True, slots=True)
class WatchRow:
    """One watchlist item. Removing it marks it inactive."""

    chain: str
    address: str
    symbol: str | None
    note: str
    source: str
    active: bool


@dataclass(frozen=True, slots=True)
class CycleSnapshot:
    """The latest stored cycle plus the current watchlist."""

    cycle_id: int
    status: str
    started_at: str
    finished_at: str | None
    chain: str
    weight_used: int
    request_count: int
    trending_count: int
    launch_count: int
    analysed_count: int
    note: str | None
    discoveries: tuple[DiscoveryRow, ...]
    rankings: tuple[RankRow, ...]
    analyses: tuple[AnalysisDetail, ...]
    watches: tuple[WatchRow, ...]


class RadarStore(Protocol):
    """Persistence used by the cycle, the API, and the terminal."""

    def save_cycle(self, cycle: StoredCycle) -> int:
        """Insert a cycle and return its id."""

    def latest_snapshot(self) -> CycleSnapshot | None:
        """Return the newest cycle, or None when no cycle has been stored."""

    def latest_liquidity(self, chain: str, address: str) -> Decimal | None:
        """Return the previous stored liquidity figure, if one exists."""

    def add_watch(
        self,
        chain: str,
        address: str,
        symbol: str | None,
        note: str,
        source: str,
    ) -> WatchRow:
        """Add or reactivate a watchlist row."""

    def deactivate_watch(self, chain: str, address: str) -> bool:
        """Mark a watch inactive. Return False when no active row exists."""

    def list_watches(self) -> tuple[WatchRow, ...]:
        """Return every watchlist row, including inactive ones."""
