"""Load stored simulation reports off the UI thread."""

from __future__ import annotations

import base64
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from apps.desktop.services.loopback_api import request_json
from config.settings import Settings
from database.repositories.simulation import PostgresSimulationRepository
from domain.exceptions import CyvoraError, DatabaseNotConfiguredError


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


class SimulationApiWorker(QThread):
    """Call one loopback simulation route. The UI thread does not wait on it."""

    finished_ok = Signal(str, str, object)
    failed = Signal(str)

    def __init__(self, settings: Settings, action: str, target: str, payload: object) -> None:
        super().__init__()
        self._settings = settings
        self._action = action
        self._target = target
        self._payload = payload

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            result = _dispatch(self._settings, self._action, self._payload)
        except CyvoraError as exc:
            self.failed.emit(str(exc))
            return
        except Exception:
            self.failed.emit("The simulation request could not be completed.")
            return
        if not self.isInterruptionRequested():
            self.finished_ok.emit(self._action, self._target, result)


def _dispatch(settings: Settings, action: str, payload: object) -> object:
    if action == "list":
        datasets = request_json(settings, "GET", "/trading/simulation/datasets")
        runs = request_json(settings, "GET", "/trading/simulation/runs")
        audits = request_json(settings, "GET", "/trading/simulation/audits")
        return {"datasets": datasets, "runs": runs, "audits": audits}
    if not isinstance(payload, dict):
        raise CyvoraError("The simulation request is invalid.")
    if action == "import":
        return request_json(settings, "POST", "/trading/simulation/imports", _import_body(payload))
    if action == "collect":
        body = {
            "dataset_id": payload.get("dataset_id", ""),
            "name": payload.get("name", ""),
            "selection_note": payload.get("selection_note", ""),
            "source": payload.get("source", "radar_candle"),
            "mint": payload.get("mint", ""),
            "symbol": payload.get("symbol", "TOKEN"),
            "resolution": payload.get("resolution"),
        }
        return request_json(settings, "POST", "/trading/simulation/collections", body)
    if action == "quality":
        dataset_id = payload.get("dataset_id")
        if not isinstance(dataset_id, str) or not dataset_id:
            raise CyvoraError("Choose a stored dataset before checking quality.")
        return request_json(
            settings,
            "POST",
            f"/trading/simulation/datasets/{dataset_id}/quality",
            {},
        )
    if action == "backtest":
        return request_json(settings, "POST", "/trading/simulation/backtests", payload)
    if action == "compare":
        return request_json(settings, "POST", "/trading/simulation/comparisons", payload)
    if action == "paper":
        return request_json(settings, "POST", "/trading/simulation/paper", payload)
    raise CyvoraError("That simulation action is not available.")


def _import_body(payload: dict[str, object]) -> dict[str, object]:
    path_value = payload.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise CyvoraError("Choose a CSV or Parquet file to import.")
    path = Path(path_value)
    if not path.is_file():
        raise CyvoraError("The import file was not found.")
    raw = path.read_bytes()
    if len(raw) > 8_000_000:
        raise CyvoraError("The import file is larger than the local limit.")
    fmt = payload.get("format")
    if fmt == "csv":
        content: str = raw.decode("utf-8")
    elif fmt == "parquet":
        content = base64.b64encode(raw).decode("ascii")
    else:
        raise CyvoraError("The import format must be csv or parquet.")
    return {
        "dataset_id": payload.get("dataset_id", ""),
        "name": payload.get("name", ""),
        "selection_note": payload.get("selection_note", ""),
        "format": fmt,
        "content": content,
        "source": "file_import",
    }


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
