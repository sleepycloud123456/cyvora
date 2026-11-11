"""Stored paper orders, positions, and strategies."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from apps.desktop.components.disclosure import DetailDisclosure
from domain.terminal import PositionLine
from domain.trading import OrderRecord, PositionRecord, TradingSnapshot
from intelligence.numbers import format_decimal
from terminal.present import money as shown_money

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

    strategy_start = Signal(str)
    strategy_stop = Signal(str)

    def __init__(self, kind: str) -> None:
        super().__init__()
        self.kind = kind
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(16)
        self.notice = QLabel()
        self.notice.setObjectName("EmptyState")
        self.notice.setWordWrap(True)
        headers = _COLUMNS[kind]
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(list(headers))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.performance = QLabel("")
        self.performance.setObjectName("Notice")
        self.performance.setWordWrap(True)
        self.detail = QLabel("")
        self.detail.setObjectName("Notice")
        self.detail.setWordWrap(True)
        self.details = DetailDisclosure("Details")
        self.details.add(self.detail)
        self.details.add(self.performance)
        layout.addWidget(self.notice)
        self.strategy_id: QLineEdit | None = None
        if kind == "strategies":
            controls = QHBoxLayout()
            controls.setSpacing(12)
            self.strategy_id = QLineEdit()
            self.strategy_id.setPlaceholderText("Registered strategy id")
            start = QPushButton("Start")
            start.setObjectName("SecondaryButton")
            stop = QPushButton("Stop")
            stop.setObjectName("SecondaryButton")
            start.clicked.connect(self._emit_start)
            stop.clicked.connect(self._emit_stop)
            controls.addWidget(self.strategy_id, stretch=1)
            controls.addWidget(start)
            controls.addWidget(stop)
            layout.addLayout(controls)
            self.performance.setText(
                "Start and stop change the paper registry only. Neither submits an order."
            )
        layout.addWidget(self.details)
        layout.addWidget(self.table, stretch=1)
        self.show_message("Trading storage has not been read.")

    def show_performance(self, text: str) -> None:
        self.performance.setText(text)

    def show_position_lines(self, lines: tuple[PositionLine, ...]) -> None:
        if self.kind != "positions":
            return
        if not lines:
            self.show_message("No simulated positions are stored.")
            return
        self.notice.setVisible(False)
        self.table.setVisible(True)
        self.detail.setText(
            "Open paper positions with stored marks and Shield plans. "
            "A mark is not a fill. A planned stop is not a guaranteed exit."
        )
        self.details.setVisible(True)
        headers = (
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
        )
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(list(headers))
        self.table.setRowCount(len(lines))
        for row_index, line in enumerate(lines):
            trailing = "not stored" if line.trailing_active is None else str(line.trailing_active)
            holding = "not stored" if line.holding_seconds is None else str(line.holding_seconds)
            values = (
                line.symbol,
                shown_money(line.quantity),
                shown_money(line.entry_price),
                shown_money(line.current_price),
                shown_money(line.position_value),
                shown_money(line.unrealized_pnl),
                shown_money(line.stop_price),
                trailing,
                line.take_profits,
                holding,
                line.strategy_id or "not stored",
                line.risk_level,
            )
            for column, value in enumerate(values):
                self.table.setItem(row_index, column, QTableWidgetItem(value))

    def _emit_start(self) -> None:
        if self.strategy_id is None:
            return
        self.strategy_start.emit(self.strategy_id.text().strip())

    def _emit_stop(self) -> None:
        if self.strategy_id is None:
            return
        self.strategy_stop.emit(self.strategy_id.text().strip())

    def show_message(self, text: str) -> None:
        self.notice.setText(text)
        self.notice.setVisible(True)
        self.detail.setText("")
        self.details.setVisible(self.performance.text() != "")
        self.table.setRowCount(0)
        self.table.setVisible(False)

    def show_snapshot(self, snapshot: TradingSnapshot) -> None:
        headers = _COLUMNS[self.kind]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(list(headers))
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
        self.notice.setVisible(False)
        self.detail.setText(
            "Simulated paper records stored by CYVORA. "
            "These are not wallet balances or chain transactions."
        )
        self.details.setVisible(True)
        self.table.setVisible(True)
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
