"""Stored backtests and modeled paper fills. The page does not invent results."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from apps.desktop.components.disclosure import DetailDisclosure


class SimulationPage(QWidget):
    """Show stored simulation text or an explicit empty state."""

    def __init__(self, kind: str) -> None:
        super().__init__()
        self._kind = kind
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(16)
        self.notice = QLabel()
        self.notice.setObjectName("EmptyState")
        self.notice.setWordWrap(True)
        self.report = QLabel("")
        self.report.setObjectName("Notice")
        self.report.setWordWrap(True)
        self.disclaimer = QLabel("")
        self.disclaimer.setObjectName("Notice")
        self.disclaimer.setWordWrap(True)
        self.details = DetailDisclosure("Details")
        self.details.add(self.disclaimer)
        layout.addWidget(self.notice)
        layout.addWidget(self.report)
        layout.addWidget(self.details)
        layout.addStretch(1)
        self.show_message("Simulation storage has not been read.")

    def show_message(self, text: str) -> None:
        self.notice.setText(text)
        self.notice.setVisible(True)
        self.report.setText("")
        self.report.setVisible(False)
        self.disclaimer.setText("")
        self.details.setVisible(False)

    def show_summary(self, text: str) -> None:
        prefix = (
            "Stored paper-broker assumptions. These are not wallet fills."
            if self._kind == "paper"
            else "Stored backtests and walk-forward reports. Parameters are not deployed."
        )
        self.notice.setVisible(False)
        self.report.setText(text)
        self.report.setVisible(True)
        self.disclaimer.setText(prefix)
        self.details.setVisible(True)
