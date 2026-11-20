"""In-memory paper audit log for tests and one process."""

from __future__ import annotations

from datetime import datetime

from domain.exceptions import TradingValidationError
from domain.trading import StrategyAudit

_ACTIONS = frozenset({"skipped", "refused", "submitted", "duplicate", "blocked"})


class MemoryAuditLog:
    """Keep evaluation rows in the process. Live trading cannot be recorded."""

    def __init__(self) -> None:
        self.rows: list[StrategyAudit] = []

    def append(self, row: StrategyAudit) -> None:
        if row.live_trading_enabled:
            raise TradingValidationError("A paper audit cannot enable live trading.")
        if row.action not in _ACTIONS:
            raise TradingValidationError("That paper audit action is not stored.")
        self.rows.append(row)

    def submitted_since(self, strategy_id: str, since: datetime) -> int:
        return sum(
            1
            for row in self.rows
            if row.strategy_id == strategy_id
            and row.action == "submitted"
            and row.created_at >= since
        )
