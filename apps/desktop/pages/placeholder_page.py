"""Explicit placeholder for pages that are not part of Phase 1."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderPage(QWidget):
    """Tells the operator that a navigation entry has no data yet."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        self.body = QLabel()
        self.body.setObjectName("Notice")
        self.body.setWordWrap(True)
        layout.addWidget(self.body)
        layout.addStretch(1)
        self.show_page("This page")

    def show_page(self, name: str) -> None:
        self.body.setText(
            f"Placeholder. {name} is not implemented in Phase 5. "
            "No live orders, wallet balances, or sample trades are shown here."
        )
