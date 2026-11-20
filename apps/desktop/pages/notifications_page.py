"""Local notification list. Telegram is sent only by the opt-in worker."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from apps.desktop.components.disclosure import DetailDisclosure
from domain.terminal import NotificationRecord

_TELEGRAM = {"sent": "sent", "failed": "failed"}

_COLUMNS = ("Evidence", "Category", "Subject", "Detail", "Desktop", "Telegram")


class NotificationsPage(QWidget):
    """Show stored notices. A quiet-period row stays marked withheld."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(16)
        self.notice = QLabel("Terminal storage has not been read.")
        self.notice.setObjectName("EmptyState")
        self.notice.setWordWrap(True)
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.footer = QLabel(
            "Application-stopped notices come from a process stop. "
            "Smart-money accumulation notices come from a stored wallet-tag count that "
            "rose between cycles. Telegram stays off unless CYVORA_TELEGRAM_ENABLED is set. "
            "The bot token is not shown. Real execution notices are not emitted."
        )
        self.footer.setObjectName("Notice")
        self.footer.setWordWrap(True)
        self.context = QLabel("")
        self.context.setObjectName("Notice")
        self.context.setWordWrap(True)
        self.details = DetailDisclosure("Details")
        self.details.add(self.context)
        self.details.add(self.footer)
        layout.addWidget(self.notice)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(self.details)

    def show_message(self, text: str) -> None:
        self.notice.setText(text)
        self.notice.setVisible(True)
        self.context.setText("")
        self.table.setRowCount(0)
        self.table.setVisible(False)

    def show_notifications(self, rows: tuple[NotificationRecord, ...]) -> None:
        if not rows:
            self.notice.setText("No stored notification matches the current book.")
            self.notice.setVisible(True)
            self.context.setText("")
            self.table.setRowCount(0)
            self.table.setVisible(False)
            return
        self.notice.setVisible(False)
        self.context.setText(
            "Local notices derived from stored rows. A withheld row fell in the quiet period. "
            "Telegram stays off unless the environment opt-in is set."
        )
        self.table.setVisible(True)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            delivery = "withheld during quiet period" if row.withheld else "shown"
            values = (
                row.evidence_at.isoformat(),
                row.category,
                row.subject,
                row.detail,
                delivery,
                _TELEGRAM.get(row.telegram_state, "not sent"),
            )
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))
