"""Store contract for paper orders. PostgreSQL is the system of record."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from domain.shield import ShieldDecisionRecord, ShieldNotice, ShieldSnapshot
from domain.trading import (
    OrderRecord,
    PositionRecord,
    ReconciliationRecord,
    SolanaInstrument,
    StrategyRecord,
    TradingSnapshot,
)


@dataclass(frozen=True)
class OrderEventWrite:
    """One event to insert with a new order."""

    state_value: str
    note: str
    recorded_at: datetime


@dataclass(frozen=True)
class LedgerContext:
    """Rows the gateway may read while the store holds its lock."""

    existing: OrderRecord | None
    position: PositionRecord | None
    positions: tuple[PositionRecord, ...]
    orders: tuple[OrderRecord, ...]
    shield: ShieldSnapshot


@dataclass(frozen=True)
class PaperCommit:
    """A finished paper attempt. ``unchanged`` means the key was already stored."""

    order: OrderRecord
    events: tuple[OrderEventWrite, ...]
    position: PositionRecord | None
    instrument: SolanaInstrument | None
    unchanged: bool
    shield: ShieldSnapshot | None = None
    shield_record: ShieldDecisionRecord | None = None
    notices: tuple[ShieldNotice, ...] = ()


PaperBuilder = Callable[[LedgerContext], PaperCommit]


class TradingStore(Protocol):
    """Persistence used by the gateway and the strategy manager."""

    def commit_paper(
        self,
        idempotency_key: str,
        mint: str,
        build: PaperBuilder,
    ) -> OrderRecord:
        """Lock the key and the position, then insert at most one execution."""

    def get_order(self, client_order_id: str) -> OrderRecord | None:
        """Return one stored order."""

    def save_reconciliation(
        self,
        order: OrderRecord,
        record: ReconciliationRecord,
        *,
        changed: bool,
    ) -> ReconciliationRecord:
        """Store the comparison. A conflict updates the order and leaves the position."""

    def list_orders(self) -> tuple[OrderRecord, ...]:
        """Return stored orders, oldest first."""

    def list_positions(self) -> tuple[PositionRecord, ...]:
        """Return open and flat positions."""

    def save_strategy(self, record: StrategyRecord) -> StrategyRecord:
        """Insert or replace one strategy row."""

    def get_strategy(self, strategy_id: str) -> StrategyRecord | None:
        """Return one strategy."""

    def list_strategies(self) -> tuple[StrategyRecord, ...]:
        """Return strategies in id order."""

    def stop_running_strategies(self, now: datetime) -> int:
        """Persist STOPPED for every RUNNING strategy. Returns how many changed."""

    def snapshot(self) -> TradingSnapshot:
        """Read the ledger for the terminal."""

    def load_shield(self) -> ShieldSnapshot:
        """Return the persisted risk book, or the documented defaults."""

    def save_shield(
        self,
        snapshot: ShieldSnapshot,
        record: ShieldDecisionRecord | None = None,
        notices: tuple[ShieldNotice, ...] = (),
    ) -> None:
        """Persist a risk book. A record with live trading enabled is rejected."""

    def list_notices(self) -> tuple[ShieldNotice, ...]:
        """Return the latest local Shield notes, oldest first."""

    def list_decisions(self) -> tuple[ShieldDecisionRecord, ...]:
        """Return the latest paper decisions, oldest first."""
