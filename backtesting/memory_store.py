"""In-memory simulation catalog for tests. It is not a stand-in for PostgreSQL."""

from __future__ import annotations

from datetime import datetime

from backtesting.history import require_dataset
from backtesting.reports import dump_report
from domain.simulation import (
    DatasetQuality,
    ExecutionAssumption,
    HistoricalDataset,
    SimulationReport,
)


class MemorySimulationStore:
    """Keep datasets and reports in the process. Live flags stay false."""

    def __init__(self) -> None:
        self.datasets: dict[str, HistoricalDataset] = {}
        self.runs: list[dict[str, object]] = []
        self.assumptions: list[ExecutionAssumption] = []
        self.qualities: list[DatasetQuality] = []
        self.collections: list[tuple[str, str, str, int, datetime]] = []

    def save_dataset(self, dataset: HistoricalDataset, now: datetime) -> HistoricalDataset:
        del now
        checked = require_dataset(dataset)
        self.datasets[checked.dataset_id] = checked
        return checked

    def get_dataset(self, dataset_id: str) -> HistoricalDataset | None:
        return self.datasets.get(dataset_id)

    def list_datasets(self) -> tuple[tuple[str, str], ...]:
        return tuple((item.dataset_id, item.name) for item in self.datasets.values())

    def save_run(self, report: SimulationReport) -> None:
        if report.parameters_deployed:
            from domain.exceptions import TradingValidationError

            raise TradingValidationError("A simulation cannot deploy parameters.")
        payload = dump_report(report)
        payload["parameters_deployed"] = False
        self.runs.append(payload)

    def list_runs(self) -> tuple[dict[str, object], ...]:
        return tuple(self.runs)

    def save_assumption(self, row: ExecutionAssumption, now: datetime) -> None:
        del now
        if row.live_trading_enabled or not row.simulated:
            from domain.exceptions import TradingValidationError

            raise TradingValidationError("A paper assumption cannot enable live trading.")
        self.assumptions.append(row)

    def list_assumptions(self) -> tuple[ExecutionAssumption, ...]:
        return tuple(self.assumptions)

    def save_quality(self, report: DatasetQuality) -> None:
        if report.live_trading_enabled:
            from domain.exceptions import TradingValidationError

            raise TradingValidationError("A quality report cannot enable live trading.")
        self.qualities.append(report)

    def latest_quality(self, dataset_id: str) -> DatasetQuality | None:
        matches = [item for item in self.qualities if item.dataset_id == dataset_id]
        if not matches:
            return None
        return matches[-1]

    def record_collection(
        self,
        dataset_id: str,
        source: str,
        detail: str,
        bar_count: int,
        collected_at: datetime,
    ) -> None:
        self.collections.append((dataset_id, source, detail, bar_count, collected_at))
