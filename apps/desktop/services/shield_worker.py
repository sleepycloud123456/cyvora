"""Load the Shield book off the UI thread."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from config.settings import Settings
from database.repositories.trading import PostgresTradingRepository
from domain.exceptions import DatabaseNotConfiguredError


class ShieldLoadWorker(QThread):
    """Read stored paper risk rows. The thread does not call GMGN or a signer."""

    loaded = Signal(object, object)
    failed = Signal(str)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            repository = PostgresTradingRepository(self._settings)
            snapshot = repository.load_shield()
            notices = repository.list_notices()
        except DatabaseNotConfiguredError:
            self.failed.emit("Shield storage is not configured. No portfolio valuation is shown.")
            return
        except Exception:
            self.failed.emit("Stored Shield records could not be read.")
            return
        if self.isInterruptionRequested():
            return
        self.loaded.emit(snapshot, notices)
