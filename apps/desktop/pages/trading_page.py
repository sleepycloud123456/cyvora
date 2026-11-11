"""Stored paper orders, positions, and strategies."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from domain.trading import OrderRecord, PositionRecord, TradingSnapshot
from intelligence.numbers import format_decimal

_COLUMNS = {
    "positions": ("Mint", "Quantity", "Average price", "Cost", "Realized", "Quote"),
    "orders": (
        "Order",
        "Strategy",
        "Symbol",
        "Side",
        "State",
        "Quantity",
        "Filled",
        "Fill price",
        "Shield",
    ),
    "strategies": ("Id", "Name", "State"),
}


class TradingPage(QWidget):
    """Show the stored simulation ledger or an explicit empty state."""

    def __init__(self, kind: str) -> None:
        super().__init__()
        self.kind = kind
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        self.notice = QLabel()
        self.notice.setObjectName("Notice")
        self.notice.setWordWrap(True)
        headers = _COLUMNS[kind]
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(list(headers))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.notice)
        layout.addWidget(self.table, stretch=1)
        self.show_message("Trading storage has not been read.")

    def show_message(self, text: str) -> None:
        self.notice.setText(text)
        self.table.setRowCount(0)

    def show_snapshot(self, snapshot: TradingSnapshot) -> None:
        if self.kind == "positions":
            rows = [_position_row(position) for position in snapshot.positions]
            empty = "No simulated positions are stored."
        elif self.kind == "orders":
            rows = [_order_row(order) for order in snapshot.orders]
            empty = "No simulated orders are stored."
        else:
            rows = [
                (strategy.strategy_id, strategy.name, strategy.state.value)
                for strategy in snapshot.strategies
            ]
            empty = "No strategies are registered."
        if not rows:
            self.show_message(empty)
            return
        self.notice.setText(
            "Simulated paper records stored by CYVORA. "
            "These are not wallet balances or chain transactions."
        )
        self.table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row_index, column, QTableWidgetItem(value))


def _money(value: Decimal | None) -> str:
    if value is None:
        return "none"
    text = format_decimal(value)
    return text if text is not None else "none"


def _position_row(position: PositionRecord) -> tuple[str, ...]:
    return (
        position.mint,
        _money(position.quantity),
        _money(position.average_price),
        _money(position.cost_quote),
        _money(position.realized_pnl_quote),
        position.quote_symbol,
    )


def _order_row(order: OrderRecord) -> tuple[str, ...]:
    return (
        order.client_order_id,
        order.strategy_id,
        order.symbol,
        order.side.value,
        order.state.value,
        _money(order.quantity),
        _money(order.filled_quantity),
        _money(order.fill_price),
        order.shield_decision,
    )
