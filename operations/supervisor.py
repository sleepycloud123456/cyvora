"""Run local workers for a fixed number of ticks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from domain.enums import ExecutionMode
from domain.operations import RunReport, TickResult


class Worker(Protocol):
    """One local job. ``tick`` must not submit an order."""

    kind: str

    def tick(self, now: datetime) -> TickResult:
        """Run one bounded unit of work."""


class OperationsLog(Protocol):
    """Optional persistence for a tick. Implementations must not log secrets."""

    def record_tick(
        self,
        result: TickResult,
        *,
        state: str,
        restarts: int,
        execution_mode: str,
        now: datetime,
    ) -> None:
        """Store one tick."""


class Supervisor:
    """Own the worker lifecycle for one bounded run."""

    def __init__(
        self,
        workers: tuple[Worker, ...],
        *,
        restart_limit: int,
        execution_mode: ExecutionMode,
        clock: Callable[[], datetime] | None = None,
        log: OperationsLog | None = None,
    ) -> None:
        self._workers = workers
        self._restart_limit = restart_limit
        self._execution_mode = execution_mode
        self._clock = clock or (lambda: datetime.now(UTC))
        self._log = log

    def run(self, ticks: int) -> RunReport:
        if ticks < 1:
            raise ValueError("A supervisor run needs at least one tick.")
        results: list[TickResult] = []
        failures = 0
        critical = False
        for _ in range(ticks):
            for worker in self._workers:
                result, restarts = self._run_worker(worker)
                if result.status == "failed":
                    failures += 1
                critical = critical or result.critical
                results.append(result)
                self._record(result, restarts)
        return RunReport(
            ticks=ticks,
            failures=failures,
            critical_failure=critical,
            results=tuple(results),
        )

    def _run_worker(self, worker: Worker) -> tuple[TickResult, int]:
        restarts = 0
        while True:
            now = self._clock()
            try:
                result = worker.tick(now)
            except Exception:
                restarts += 1
                if restarts > self._restart_limit:
                    return (
                        TickResult(
                            worker.kind,
                            "failed",
                            "The worker tick failed. The error text was withheld.",
                            critical=worker.kind == "portfolio",
                        ),
                        restarts - 1,
                    )
                continue
            return result, restarts

    def _record(self, result: TickResult, restarts: int) -> None:
        if self._log is None:
            return
        state = "failed" if result.status == "failed" else "stopped"
        try:
            self._log.record_tick(
                result,
                state=state,
                restarts=restarts,
                execution_mode=self._execution_mode.value,
                now=self._clock(),
            )
        except Exception as exc:
            from logging import getLogger

            getLogger("cyvora.operations").warning(
                "worker record failed error_type=%s", type(exc).__name__
            )
