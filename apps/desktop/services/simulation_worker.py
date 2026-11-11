"""Load stored simulation reports off the UI thread."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from config.settings import Settings
from database.repositories.simulation import PostgresSimulationRepository
from domain.exceptions import DatabaseNotConfiguredError


class SimulationLoadWorker(QThread):
    """Read stored reports. The thread does not call GMGN, a signer, or a wallet."""

    loaded = Signal(str, str)
    failed = Signal(str)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            repository = PostgresSimulationRepository(self._settings)
            runs = repository.list_runs()
            assumptions = repository.list_assumptions()
        except DatabaseNotConfiguredError:
            self.failed.emit("Simulation storage is not configured. No backtest results are shown.")
            return
        except Exception:
            self.failed.emit("Stored simulation reports could not be read.")
            return
        if self.isInterruptionRequested():
            return
        self.loaded.emit(_runs(runs), _paper(len(assumptions)))


def _runs(rows: tuple[dict[str, object], ...]) -> str:
    if not rows:
        return "No backtest is stored. Candle closes are not shown as fills."
    lines = ["Live trading is locked. A stored report did not deploy parameters."]
    for row in rows[-8:]:
        kind = row.get("kind", "backtest")
        strategy = row.get("strategy_id", "")
        performance = row.get("performance")
        net = "unmarked"
        trades = "0"
        if isinstance(performance, dict):
            net = str(performance.get("net_profit"))
            trades = str(performance.get("trade_count"))
        lines.append(f"{kind} {strategy}: net {net}, closed campaigns {trades}.")
    return "\n".join(lines)


def _paper(count: int) -> str:
    if count == 0:
        return (
            "No modeled paper fill is stored. Caller-supplied paper orders "
            "do not use the pool or fee model."
        )
    return (
        f"{count} modeled paper fill assumptions are stored. "
        "Each one was submitted through Shield. None is a chain confirmation."
    )
