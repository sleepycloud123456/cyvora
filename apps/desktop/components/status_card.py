"""Reusable status card."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from domain.status import ComponentStatus


class StatusCard(QFrame):
    """A labeled state and a short explanation."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("StatusCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        self.state_label = QLabel("Not checked")
        self.state_label.setObjectName("StateValue")
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("CardDetail")
        self.detail_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(self.state_label)
        layout.addWidget(self.detail_label)

    def set_status(self, state: str, detail: str) -> None:
        self.state_label.setText(state)
        self.detail_label.setText(detail)

    def apply(self, status: ComponentStatus) -> None:
        self.set_status(status.state, status.detail)
