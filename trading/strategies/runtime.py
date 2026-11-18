"""Connect the supervisor and the strategy start path to the paper runner."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from config.settings import Settings
from database.repositories.paper_audit import PostgresPaperAudit
from database.repositories.simulation import PostgresSimulationRepository
from database.repositories.terminal import PostgresTerminalRepository
from database.repositories.trading import PostgresTradingRepository
from domain.enums import ExecutionMode
from domain.operations import TickResult
from readiness.guard import operator_orders_blocked
from trading.strategies.runner import EvaluationSummary, evaluate_running_strategies


class PaperStrategyWorker:
    """One supervisor tick. It can submit a paper order through Shield.

    It does not sign, send an RPC transaction, or read a private key.
    """

    kind = "paper_strategy"

    def __init__(self, evaluate: Callable[[datetime], EvaluationSummary]) -> None:
        self._evaluate = evaluate

    def tick(self, now: datetime) -> TickResult:
        try:
            summary = self._evaluate(now)
        except Exception as exc:
            return TickResult(
                self.kind,
                "failed",
                f"Paper strategy evaluation failed ({type(exc).__name__}). No live order was sent.",
            )
        return TickResult(self.kind, summary.status, summary.detail)


def evaluate_stored(
    settings: Settings,
    now: datetime | None = None,
    *,
    strategy_id: str | None = None,
    entries_blocked: Callable[[], bool] | None = None,
) -> EvaluationSummary:
    """Evaluate stored RUNNING strategies. A missing database does not submit."""

    moment = now or datetime.now(UTC)
    if settings.execution_mode is not ExecutionMode.PAPER:
        return EvaluationSummary(
            "skipped",
            0,
            0,
            0,
            0,
            "Read-only mode does not evaluate paper strategies. Live trading stays locked.",
        )
    if not settings.database_url:
        return EvaluationSummary(
            "not_configured",
            0,
            0,
            0,
            0,
            "Paper strategy storage is not configured. No order was submitted.",
        )
    blocked = entries_blocked or (lambda: operator_orders_blocked(settings))
    threshold = PostgresTerminalRepository(settings).active_signal_threshold()
    return evaluate_running_strategies(
        mode=settings.execution_mode,
        store=PostgresTradingRepository(settings),
        datasets=PostgresSimulationRepository(settings),
        audits=PostgresPaperAudit(settings),
        threshold=threshold,
        now=moment,
        entries_blocked=blocked,
        strategy_id=strategy_id,
    )
