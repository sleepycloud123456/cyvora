"""Paper portfolio page. Figures come from stored rows."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from domain.terminal import PortfolioView
from terminal.present import money, portfolio_text

_COLUMNS = (
    "Token",
    "Quantity",
    "Entry",
    "Current",
    "Value",
    "Unrealized",
    "Stop",
    "Trailing",
    "Take profit",
    "Holding",
    "Strategy",
    "Risk",
    "Quote",
)


class PortfolioPage(QWidget):
    """Show the stored paper book or an explicit empty state."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        self.notice = QLabel("Terminal storage has not been read.")
        self.notice.setObjectName("Notice")
        self.notice.setWordWrap(True)
        self.summary = QLabel("")
        self.summary.setObjectName("Notice")
        self.summary.setWordWrap(True)
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.notice)
        layout.addWidget(self.summary)
        layout.addWidget(self.table, stretch=1)

    def show_message(self, text: str) -> None:
        self.notice.setText(text)
        self.summary.setText("")
        self.table.setRowCount(0)

    def show_portfolio(self, view: PortfolioView) -> None:
        self.notice.setText(
            "Stored paper portfolio. These are not wallet balances, and a mark is not a fill."
        )
        self.summary.setText(portfolio_text(view))
        self.table.setRowCount(len(view.positions))
        for row_index, line in enumerate(view.positions):
            values = (
                line.symbol,
                money(line.quantity),
                money(line.entry_price),
                _price(line.current_price, line.price_source),
                money(line.position_value),
                money(line.unrealized_pnl),
                money(line.stop_price),
                _trail(line.trailing_active),
                line.take_profits,
                _holding(line.holding_seconds),
                line.strategy_id or "not stored",
                line.risk_level,
                line.quote_symbol,
            )
            for column, value in enumerate(values):
                self.table.setItem(row_index, column, QTableWidgetItem(value))
        if not view.positions:
            self.table.setRowCount(0)


def _price(value: Decimal | None, source: str | None) -> str:
    if value is None:
        return "none"
    return f"{money(value)} ({source or 'stored'})"


def _trail(active: bool | None) -> str:
    if active is None:
        return "not stored"
    return "active" if active else "inactive"


def _holding(seconds: int | None) -> str:
    if seconds is None:
        return "not stored"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"
