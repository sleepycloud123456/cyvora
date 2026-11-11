"""Background radar cycle. The UI thread does not call GMGN."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QThread, Signal

from config.settings import Settings
from database.repositories.radar import PostgresRadarRepository
from intelligence.cycle import CycleResult, run_radar_cycle


class RadarCycleWorker(QThread):
    """Run one read-only cycle and report a status word, not an exception string."""

    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self.last_result: CycleResult | None = None

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            result = asyncio.run(
                run_radar_cycle(self._settings, PostgresRadarRepository(self._settings))
            )
        except Exception:
            self.failed.emit("The radar cycle failed. The error text was withheld.")
            return
        self.last_result = result
        if result.cycle_id is None or result.analysed_count == 0:
            self.failed.emit(
                "Radar status "
                f"{result.status}. Analysed {result.analysed_count}. No order was sent."
            )
            return
        self.finished_ok.emit(
            f"Stored cycle {result.cycle_id}: {result.trending_count} trending, "
            f"{result.launch_count} launches, {result.analysed_count} analysed. "
            "Entry is not authorized."
        )


class WatchWorker(QThread):
    """Add or remove a watchlist row off the UI thread."""

    finished_ok = Signal()
    failed = Signal(str)

    def __init__(
        self, settings: Settings, action: str, chain: str, address: str, symbol: str
    ) -> None:
        super().__init__()
        self._settings = settings
        self._action = action
        self._chain = chain
        self._address = address
        self._symbol = symbol

    def run(self) -> None:
        try:
            repository = PostgresRadarRepository(self._settings)
            if self._action == "add":
                repository.add_watch(
                    self._chain,
                    self._address,
                    self._symbol or None,
                    "Added from the scanner.",
                    "manual",
                )
            else:
                repository.deactivate_watch(self._chain, self._address)
        except Exception:
            self.failed.emit(
                "The watchlist could not be updated. The database message was withheld."
            )
            return
        self.finished_ok.emit()


class RadarLoadWorker(QThread):
    """Load the latest stored cycle off the UI thread."""

    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    def run(self) -> None:
        try:
            snapshot = PostgresRadarRepository(self._settings).latest_snapshot()
        except Exception:
            self.failed.emit("Radar storage could not be read. The database message was withheld.")
            return
        self.loaded.emit(snapshot)
