"""Background status probe so the UI thread stays responsive."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from config.settings import Settings
from monitoring.health import collect_status


class StatusProbe(QThread):
    """Run the foundation checks off the UI thread."""

    snapshot_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            snapshot = collect_status(self._settings, probe_backend=True)
        except Exception:
            self.failed.emit(
                "Status check failed. The error text was withheld "
                "because it can contain configuration."
            )
            return
        if not self.isInterruptionRequested():
            self.snapshot_ready.emit(snapshot)
