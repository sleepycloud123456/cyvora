"""Stored radar results. Figures come from PostgreSQL, not from a live paint."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from apps.desktop.charts.candle_chart import CandleChart
from intelligence.store import AnalysisDetail, CycleSnapshot, DiscoveryRow, RankRow, WatchRow

_COLUMNS = (
    "Rank",
    "Symbol",
    "Name",
    "Age",
    "Price",
    "Market cap",
    "Liquidity",
    "Volume",
    "Price change",
    "Volume change",
    "Smart money",
    "Security",
    "Score",
    "Confidence",
    "Decision",
    "Warnings",
)


class RadarPage(QWidget):
    """One radar destination. It shows a stored cycle or an explicit empty state."""

    watch_add = Signal(str, str, str)
    watch_remove = Signal(str, str)

    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode
        self._snapshot: CycleSnapshot | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)
        self.summary = QLabel("Stored radar results have not been loaded.")
        self.summary.setObjectName("Notice")
        self.summary.setWordWrap(True)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter by symbol or name")
        self.filter.textChanged.connect(self._render)
        buttons = QHBoxLayout()
        self.run_button = QPushButton("Run one read-only cycle")
        self.continuous = QCheckBox("Repeat on the configured interval")
        self.watch_button = QPushButton("Add to watchlist")
        self.unwatch_button = QPushButton("Remove from watchlist")
        self.watch_button.clicked.connect(self._emit_add)
        self.unwatch_button.clicked.connect(self._emit_remove)
        if mode != "scanner":
            self.run_button.hide()
            self.continuous.hide()
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.continuous)
        buttons.addWidget(self.watch_button)
        buttons.addWidget(self.unwatch_button)
        buttons.addStretch(1)
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setObjectName("RadarTable")
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(False)
        self.table.itemSelectionChanged.connect(self._show_selection)
        self.detail = QTextEdit()
        self.detail.setObjectName("RadarDetail")
        self.detail.setReadOnly(True)
        self.chart = CandleChart()
        layout.addWidget(self.summary)
        layout.addWidget(self.filter)
        layout.addLayout(buttons)
        layout.addWidget(self.table, stretch=3)
        layout.addWidget(self.chart)
        layout.addWidget(self.detail, stretch=2)
        self.show_message("No radar cycle has been stored. This page does not invent market data.")

    def show_message(self, text: str) -> None:
        self.summary.setText(text)

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        if running:
            self.summary.setText("Read-only radar cycle is running. No order will be sent.")

    def show_snapshot(self, snapshot: CycleSnapshot | None) -> None:
        self._snapshot = snapshot
        if snapshot is None:
            self.table.setRowCount(0)
            self.detail.setPlainText("No radar cycle has been stored.")
            self.chart.set_rows([])
            if "running" not in self.summary.text():
                self.show_message(
                    "No radar cycle has been stored. This page does not invent market data."
                )
            return
        active = [watch for watch in snapshot.watches if watch.active]
        names = [watch.symbol or "unnamed" for watch in active[:8]]
        extra = f" and {len(active) - 8} more" if len(active) > 8 else ""
        listed = f" ({', '.join(names)}{extra})" if names else ""
        self.summary.setText(
            f"Stored cycle {snapshot.cycle_id}, status {snapshot.status}, "
            f"finished {snapshot.finished_at}. Not a live feed. "
            f"Active watches: {len(active)}{listed}. Entry is not authorized."
        )
        self._render()

    def selected_identity(self) -> tuple[str, str, str | None] | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        chain_item = self.table.item(row, 0)
        if chain_item is None:
            return None
        identity = chain_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(identity, tuple) or len(identity) != 3:
            return None
        chain, address, symbol = identity
        if not isinstance(chain, str) or not isinstance(address, str):
            return None
        return chain, address, symbol if isinstance(symbol, str) else None

    def _emit_add(self) -> None:
        identity = self.selected_identity()
        if identity is None:
            self.show_message("Select a stored token before adding it to the watchlist.")
            return
        chain, address, symbol = identity
        self.watch_add.emit(chain, address, symbol or "")

    def _emit_remove(self) -> None:
        identity = self.selected_identity()
        if identity is None:
            self.show_message("Select a stored token before removing it from the watchlist.")
            return
        chain, address, _symbol = identity
        self.watch_remove.emit(chain, address)

    def _render(self) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return
        needle = self.filter.text().strip().lower()
        if self.mode == "trending":
            rows = [
                _discovery_cells(row) for row in snapshot.discoveries if row.source == "trending"
            ]
        elif self.mode == "launches":
            rows = [
                _discovery_cells(row) for row in snapshot.discoveries if row.source == "new_launch"
            ]
        elif self.mode == "watches":
            rows = [_watch_cells(row) for row in snapshot.watches if row.active]
        else:
            ranked = list(snapshot.rankings)
            if self.mode == "smart":
                ranked = [row for row in ranked if row.smart_money not in {"", "missing"}]
            elif self.mode == "whale":
                ranked = [row for row in ranked if row.whale_status not in {"", "missing"}]
            rows = [_rank_cells(row) for row in ranked]
        if needle:
            rows = [
                row
                for row in rows
                if needle in str(row[1]).lower() or needle in str(row[2]).lower()
            ]
        self.table.setRowCount(len(rows))
        for index, cells in enumerate(rows):
            identity = cells[-1]
            for column, text in enumerate(cells[:-1]):
                item = QTableWidgetItem(str(text))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, identity)
                self.table.setItem(index, column, item)
        if not rows:
            self.detail.setPlainText("This view has no stored rows for the latest cycle.")
            self.chart.set_rows([])

    def _show_selection(self) -> None:
        identity = self.selected_identity()
        snapshot = self._snapshot
        if identity is None or snapshot is None:
            return
        _chain, address, _symbol = identity
        detail = next((item for item in snapshot.analyses if item.address == address), None)
        if detail is None:
            self.detail.setPlainText("No analysis was stored for this row.")
            self.chart.set_rows([])
            return
        self.detail.setPlainText(_detail_text(detail))
        self.chart.set_rows(
            [(candle[1], candle[2], candle[3], candle[4]) for candle in detail.candles]
        )


def _rank_cells(row: RankRow) -> tuple[object, ...]:
    return (
        str(row.rank),
        row.symbol or "",
        row.name or "",
        _age(row.creation_timestamp),
        row.price or "",
        row.market_cap or "",
        row.liquidity or "",
        row.volume or "",
        row.price_change or "",
        row.volume_change or "",
        row.smart_money,
        row.security_category,
        row.score or "",
        row.research_confidence or "",
        row.decision,
        "; ".join(row.warnings[:2]),
        (row.chain, row.address, row.symbol),
    )


def _discovery_cells(row: DiscoveryRow) -> tuple[object, ...]:
    return (
        row.source,
        row.symbol or "",
        row.name or "",
        _age(row.creation_timestamp),
        row.price or "",
        row.market_cap or "",
        row.liquidity or "",
        row.volume or "",
        row.price_change or "",
        "",
        "",
        "",
        "",
        "",
        row.route,
        "",
        (row.chain, row.address, row.symbol),
    )


def _watch_cells(row: WatchRow) -> tuple[object, ...]:
    return (
        "watch",
        row.symbol or "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        row.source,
        row.note,
        (row.chain, row.address, row.symbol),
    )


def _detail_text(detail: AnalysisDetail) -> str:
    lines = [
        detail.explanation,
        f"Decision {detail.decision}. Security {detail.security_category}.",
        f"Liquidity {detail.liquidity_status}. Smart money {detail.smart_money_status}.",
        f"Whales {detail.whale_status}. Entry is not authorized.",
        "Components:",
    ]
    for name, value, quality in detail.components:
        lines.append(f"- {name}: {value} ({quality})")
    if detail.warnings:
        lines.append("Warnings: " + " ".join(detail.warnings[:6]))
    return "\n".join(lines)


def _age(created: int | None) -> str:
    if created is None or created <= 0:
        return ""
    stamp = created // 1000 if created >= 10**12 else created
    seconds = int(datetime.now(UTC).timestamp()) - stamp
    if seconds < 0:
        return ""
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"
