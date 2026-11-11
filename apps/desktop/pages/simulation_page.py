"""Stored backtests and modeled paper fills. The page does not invent results."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class SimulationPage(QWidget):
    """Show stored simulation text or an explicit empty state."""

    def __init__(self, kind: str) -> None:
        super().__init__()
        self._kind = kind
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        self.notice = QLabel()
        self.notice.setObjectName("Notice")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        layout.addStretch(1)
        self.show_message("Simulation storage has not been read.")

    def show_message(self, text: str) -> None:
        self.notice.setText(text)

    def show_summary(self, text: str) -> None:
        prefix = (
            "Stored paper-broker assumptions. These are not wallet fills."
            if self._kind == "paper"
            else "Stored backtests and walk-forward reports. Parameters are not deployed."
        )
        self.notice.setText(f"{prefix}\n{text}")
