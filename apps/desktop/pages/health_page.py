"""System health page for the foundation checks."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from apps.desktop.components.status_card import StatusCard
from config.settings import PHASE, Settings
from domain.enums import ExecutionMode
from domain.status import StatusSnapshot


class HealthPage(QWidget):
    """Shows the same verified checks as the dashboard, plus the interpreter."""

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(16)
        mode = "PAPER" if settings.execution_mode is ExecutionMode.PAPER else "READ-ONLY"
        self.summary = QLabel(
            f"Phase {PHASE}. Mode {mode}. Python {sys.version.split()[0]}. "
            "Live trading is locked. These checks do not query GMGN or a wallet."
        )
        self.summary.setObjectName("Notice")
        self.summary.setWordWrap(True)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.application_card = StatusCard("Application")
        self.database_card = StatusCard("Database")
        self.backend_card = StatusCard("Backend")
        row.addWidget(self.application_card)
        row.addWidget(self.database_card)
        row.addWidget(self.backend_card)
        layout.addWidget(self.summary)
        layout.addLayout(row)
        layout.addStretch(1)

    def set_checking(self) -> None:
        for card in self._cards():
            card.set_status("Checking...", "A background status check is running.")

    def set_idle(self) -> None:
        for card in self._cards():
            card.set_status("Not checked", "The status probe is idle in this session.")

    def show_probe_failure(self, message: str) -> None:
        self.database_card.set_status("unknown", message)
        self.backend_card.set_status("unknown", message)

    def apply_snapshot(self, snapshot: StatusSnapshot) -> None:
        self.application_card.apply(snapshot.application)
        self.database_card.apply(snapshot.database)
        self.backend_card.apply(snapshot.backend)

    def _cards(self) -> tuple[StatusCard, ...]:
        return (self.application_card, self.database_card, self.backend_card)
