"""In-memory paper ledger for tests. It is not a stand-in for PostgreSQL."""

from __future__ import annotations

from datetime import datetime

from domain.trading import (
    OrderRecord,
    PositionRecord,
    ReconciliationRecord,
    StrategyRecord,
    StrategyState,
    TradingSnapshot,
)
from trading.store import PaperBuilder


class MemoryTradingStore:
    """Keep one process-local copy of the paper ledger."""

    def __init__(self) -> None:
        self.orders: dict[str, OrderRecord] = {}
        self.events: dict[str, list[tuple[str, str]]] = {}
        self.positions: dict[str, PositionRecord] = {}
        self.strategies: dict[str, StrategyRecord] = {}
        self.reconciliations: list[ReconciliationRecord] = []

    def commit_paper(
        self,
        idempotency_key: str,
        mint: str,
        build: PaperBuilder,
    ) -> OrderRecord:
        existing = next(
            (order for order in self.orders.values() if order.idempotency_key == idempotency_key),
            None,
        )
        commit = build(existing, self.positions.get(mint))
        if existing is not None or commit.unchanged:
            return existing if existing is not None else commit.order
        self.orders[commit.order.client_order_id] = commit.order
        self.events[commit.order.client_order_id] = [
            (event.state_value, event.note) for event in commit.events
        ]
        if commit.position is not None:
            self.positions[commit.position.mint] = commit.position
        return commit.order

    def get_order(self, client_order_id: str) -> OrderRecord | None:
        return self.orders.get(client_order_id)

    def save_reconciliation(
        self,
        order: OrderRecord,
        record: ReconciliationRecord,
        *,
        changed: bool,
    ) -> ReconciliationRecord:
        if changed:
            self.orders[order.client_order_id] = order
            self.events.setdefault(order.client_order_id, []).append(
                (order.state.value, record.detail)
            )
        self.reconciliations.append(record)
        return record

    def list_orders(self) -> tuple[OrderRecord, ...]:
        return tuple(self.orders.values())

    def list_positions(self) -> tuple[PositionRecord, ...]:
        return tuple(self.positions.values())

    def save_strategy(self, record: StrategyRecord) -> StrategyRecord:
        self.strategies[record.strategy_id] = record
        return record

    def get_strategy(self, strategy_id: str) -> StrategyRecord | None:
        return self.strategies.get(strategy_id)

    def list_strategies(self) -> tuple[StrategyRecord, ...]:
        return tuple(self.strategies[key] for key in sorted(self.strategies))

    def stop_running_strategies(self, now: datetime) -> int:
        changed = 0
        for strategy_id, record in list(self.strategies.items()):
            if record.state is not StrategyState.RUNNING:
                continue
            self.strategies[strategy_id] = StrategyRecord(
                strategy_id=record.strategy_id,
                name=record.name,
                state=StrategyState.STOPPED,
                parameters=record.parameters,
                registered_at=record.registered_at,
                updated_at=now,
            )
            changed += 1
        return changed

    def snapshot(self) -> TradingSnapshot:
        return TradingSnapshot(self.list_orders(), self.list_positions(), self.list_strategies())
