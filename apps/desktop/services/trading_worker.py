"""Load the paper ledger off the UI thread."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from config.settings import Settings
from database.repositories.trading import PostgresTradingRepository
from domain.exceptions import DatabaseNotConfiguredError


class TradingLoadWorker(QThread):
    """Read stored simulation rows. The thread does not call GMGN."""

    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            snapshot = PostgresTradingRepository(self._settings).snapshot()
        except DatabaseNotConfiguredError:
            self.failed.emit("Trading storage is not configured. No simulated orders are shown.")
            return
        except Exception:
            self.failed.emit("Stored simulation records could not be read.")
            return
        if self.isInterruptionRequested():
            return
        self.loaded.emit(snapshot)
