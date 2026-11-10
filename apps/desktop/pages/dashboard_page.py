"""Dashboard placeholder with real foundation status."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from apps.desktop.components.status_card import StatusCard
from domain.status import StatusSnapshot


class DashboardPage(QWidget):
    """Status dashboard. It does not invent portfolio or market figures."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(16)
        self.notice = QLabel(
            "Phase 2 shows whether a GMGN API key is configured. Portfolio value, "
            "token prices, positions, and profit figures are not available on this "
            "page and are not displayed."
        )
        self.notice.setObjectName("Notice")
        self.notice.setWordWrap(True)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.application_card = StatusCard("Application")
        self.database_card = StatusCard("Database")
        self.backend_card = StatusCard("Backend")
        self.gmgn_card = StatusCard("GMGN")
        row.addWidget(self.application_card)
        row.addWidget(self.database_card)
        row.addWidget(self.backend_card)
        row.addWidget(self.gmgn_card)
        layout.addWidget(self.notice)
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
        self.gmgn_card.set_status("unknown", message)

    def apply_snapshot(self, snapshot: StatusSnapshot) -> None:
        self.application_card.apply(snapshot.application)
        self.database_card.apply(snapshot.database)
        self.backend_card.apply(snapshot.backend)
        self.gmgn_card.apply(snapshot.gmgn)

    def _cards(self) -> tuple[StatusCard, ...]:
        return (self.application_card, self.database_card, self.backend_card, self.gmgn_card)
