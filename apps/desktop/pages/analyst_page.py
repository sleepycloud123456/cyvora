"""Local analyst. It explains stored rows and cannot authorize an order."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from domain.terminal import AnalystReport
from terminal.present import analyst_text


class AnalystPage(QWidget):
    """Show the stored-evidence report or an explicit empty state."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        self.notice = QLabel("Terminal storage has not been read.")
        self.notice.setObjectName("Notice")
        self.notice.setWordWrap(True)
        self.body = QTextEdit()
        self.body.setReadOnly(True)
        layout.addWidget(self.notice)
        layout.addWidget(self.body, stretch=1)

    def show_message(self, text: str) -> None:
        self.notice.setText(text)
        self.body.setPlainText("")

    def show_report(self, report: AnalystReport) -> None:
        self.notice.setText(
            "Local stored-evidence analyst. No external model is called. "
            "Findings are advisory and cannot authorize an order."
        )
        self.body.setPlainText(analyst_text(report))
