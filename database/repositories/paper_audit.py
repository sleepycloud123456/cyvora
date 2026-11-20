"""PostgreSQL audit log for supervised paper strategies."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import Settings
from database.connection import create_database_engine
from database.models.simulation import PaperStrategyAuditRow
from domain.exceptions import (
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    TradingValidationError,
)
from domain.trading import StrategyAudit

logger = logging.getLogger("cyvora.strategy_audit")

_ACTIONS = frozenset({"skipped", "refused", "submitted", "duplicate", "blocked"})


class PostgresPaperAudit:
    """Append-only paper evaluation log. A row cannot enable live trading."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def append(self, row: StrategyAudit) -> None:
        if row.live_trading_enabled:
            raise TradingValidationError("A paper audit cannot enable live trading.")
        if row.action not in _ACTIONS:
            raise TradingValidationError("That paper audit action is not stored.")
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                session.add(
                    PaperStrategyAuditRow(
                        strategy_id=row.strategy_id[:48],
                        action=row.action,
                        reason=row.reason[:240],
                        signal_strength=(
                            None if row.signal_strength is None else row.signal_strength[:32]
                        ),
                        threshold=None if row.threshold is None else row.threshold[:32],
                        client_order_id=row.client_order_id,
                        created_at=row.created_at,
                        live_trading_enabled=False,
                    )
                )
                session.commit()
        except (DatabaseNotConfiguredError, DatabaseUnavailableError, TradingValidationError):
            raise
        except Exception as exc:
            logger.warning("paper audit failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The paper audit could not be stored.") from None
        finally:
            engine.dispose()

    def submitted_since(self, strategy_id: str, since: datetime) -> int:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                rows = session.scalars(
                    select(PaperStrategyAuditRow).where(
                        PaperStrategyAuditRow.strategy_id == strategy_id,
                        PaperStrategyAuditRow.action == "submitted",
                        PaperStrategyAuditRow.created_at >= since,
                    )
                ).all()
                return len(rows)
        except (DatabaseNotConfiguredError, DatabaseUnavailableError):
            raise
        except Exception as exc:
            logger.warning("paper audit read failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The paper audit could not be read.") from None
        finally:
            engine.dispose()

    def list_recent(self, limit: int = 50) -> tuple[StrategyAudit, ...]:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                rows = session.scalars(
                    select(PaperStrategyAuditRow)
                    .order_by(PaperStrategyAuditRow.created_at.desc())
                    .limit(limit)
                ).all()
                return tuple(_audit(row) for row in reversed(rows))
        except (DatabaseNotConfiguredError, DatabaseUnavailableError):
            raise
        except Exception as exc:
            logger.warning("paper audit list failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The paper audit could not be read.") from None
        finally:
            engine.dispose()


def _audit(row: PaperStrategyAuditRow) -> StrategyAudit:
    return StrategyAudit(
        strategy_id=row.strategy_id,
        action=row.action,
        reason=row.reason,
        signal_strength=row.signal_strength,
        threshold=row.threshold,
        client_order_id=row.client_order_id,
        created_at=row.created_at,
        live_trading_enabled=False,
    )
