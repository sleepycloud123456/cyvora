"""Local notification list. Telegram is not sent."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from domain.terminal import UNSOURCED_NOTIFICATIONS, NotificationRecord

_COLUMNS = ("Evidence", "Category", "Subject", "Detail", "Desktop", "Telegram")


class NotificationsPage(QWidget):
    """Show stored notices. A quiet-period row stays marked withheld."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        self.notice = QLabel("Terminal storage has not been read.")
        self.notice.setObjectName("Notice")
        self.notice.setWordWrap(True)
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        missing = ", ".join(sorted(item.value for item in UNSOURCED_NOTIFICATIONS))
        self.footer = QLabel(
            "Smart-money accumulation and application-stopped have no stored source, "
            f"so they are not emitted ({missing}). Real execution notices are not emitted. "
            "Telegram delivery is off because no bot token is loaded."
        )
        self.footer.setObjectName("Notice")
        self.footer.setWordWrap(True)
        layout.addWidget(self.notice)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(self.footer)

    def show_message(self, text: str) -> None:
        self.notice.setText(text)
        self.table.setRowCount(0)

    def show_notifications(self, rows: tuple[NotificationRecord, ...]) -> None:
        if not rows:
            self.notice.setText("No stored notification matches the current book.")
            self.table.setRowCount(0)
            return
        self.notice.setText(
            "Local notices derived from stored rows. A withheld row fell in the quiet period. "
            "Nothing was sent to Telegram."
        )
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            delivery = "withheld during quiet period" if row.withheld else "shown"
            values = (
                row.evidence_at.isoformat(),
                row.category,
                row.subject,
                row.detail,
                delivery,
                "not sent",
            )
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))
