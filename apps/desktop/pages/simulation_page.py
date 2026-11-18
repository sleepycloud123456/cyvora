"""Paper trading and backtesting. The page shows stored results and does not invent fills."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from apps.desktop.charts.series_chart import SeriesChart
from apps.desktop.components.disclosure import DetailDisclosure


class SimulationPage(QWidget):
    """Dataset import, a run, stored results, and manual paper entry."""

    refresh_requested = Signal()
    import_requested = Signal(object)
    collect_requested = Signal(object)
    quality_requested = Signal(object)
    run_requested = Signal(object)
    compare_requested = Signal(object)
    paper_requested = Signal(object)

    def __init__(self, kind: str, *, paper_enabled: bool = False) -> None:
        super().__init__()
        self.kind = kind
        self.paper_enabled = paper_enabled
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.notice = QLabel("Simulation storage has not been read.")
        self.notice.setObjectName("EmptyState")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        form = QFormLayout()
        form.setSpacing(8)
        self.dataset = QComboBox()
        self.dataset_id = QLineEdit()
        self.dataset_id.setPlaceholderText("dataset id")
        self.dataset_name = QLineEdit()
        self.dataset_name.setPlaceholderText("Dataset name")
        self.selection_note = QLineEdit()
        self.selection_note.setPlaceholderText("Selection note, 12 to 240 characters")
        self.import_path = QLineEdit()
        self.import_path.setPlaceholderText("CSV or Parquet file")
        self.import_format = QComboBox()
        self.import_format.addItems(["csv", "parquet"])
        browse = QPushButton("Browse")
        browse.setObjectName("SecondaryButton")
        browse.clicked.connect(self._browse)
        import_button = QPushButton("Import")
        import_button.setObjectName("SecondaryButton")
        import_button.clicked.connect(self._emit_import)
        path_row = QHBoxLayout()
        path_row.addWidget(self.import_path, stretch=1)
        path_row.addWidget(self.import_format)
        path_row.addWidget(browse)
        path_row.addWidget(import_button)
        self.collect_source = QComboBox()
        self.collect_source.addItem("Stored radar candles", "radar_candle")
        self.collect_source.addItem("GMGN kline", "gmgn_kline")
        self.collect_source.addItem("Adapter quotes", "solana_adapter")
        self.collect_mint = QLineEdit()
        self.collect_mint.setPlaceholderText("Mint")
        self.collect_symbol = QLineEdit()
        self.collect_symbol.setPlaceholderText("Symbol")
        self.resolution = QComboBox()
        self.resolution.addItems(["1m", "5m", "15m", "1h"])
        collect = QPushButton("Collect")
        collect.setObjectName("SecondaryButton")
        collect.clicked.connect(self._emit_collect)
        collect_row = QHBoxLayout()
        collect_row.addWidget(self.collect_source)
        collect_row.addWidget(self.collect_mint, stretch=1)
        collect_row.addWidget(self.collect_symbol)
        collect_row.addWidget(self.resolution)
        collect_row.addWidget(collect)
        self.strategy = QComboBox()
        self.strategy.addItems(["momentum", "breakout", "signal-follow"])
        self.lookback = QLineEdit("2")
        self.entry_return = QLineEdit("0.05")
        self.stop_fraction = QLineEdit("0.10")
        self.starting_equity = QLineEdit("1000")
        self.instrument_mint = QLineEdit()
        self.instrument_mint.setPlaceholderText("Instrument mint")
        self.instrument_symbol = QLineEdit()
        self.instrument_symbol.setPlaceholderText("Symbol")
        self.size_decimals = QLineEdit("6")
        self.price_decimals = QLineEdit("6")
        self.quote_symbol = QLineEdit("SOL")
        self.quote_decimals = QLineEdit("9")
        refresh = QPushButton("Refresh")
        refresh.setObjectName("SecondaryButton")
        refresh.clicked.connect(self.refresh_requested.emit)
        header = QHBoxLayout()
        header.addWidget(self.dataset, stretch=1)
        header.addWidget(refresh)
        form.addRow("Dataset", header)
        form.addRow("Dataset id", self.dataset_id)
        form.addRow("Name", self.dataset_name)
        form.addRow("Selection note", self.selection_note)
        form.addRow("File", path_row)
        form.addRow("Collect", collect_row)
        form.addRow("Strategy", self.strategy)
        form.addRow("Lookback", self.lookback)
        form.addRow("Entry return", self.entry_return)
        form.addRow("Stop fraction", self.stop_fraction)
        form.addRow("Starting equity", self.starting_equity)
        form.addRow("Mint", self.instrument_mint)
        form.addRow("Symbol", self.instrument_symbol)
        layout.addLayout(form)
        details = DetailDisclosure("Instrument precision")
        precision = QWidget()
        precision_form = QFormLayout(precision)
        precision_form.addRow("Size decimals", self.size_decimals)
        precision_form.addRow("Price decimals", self.price_decimals)
        precision_form.addRow("Quote", self.quote_symbol)
        precision_form.addRow("Quote decimals", self.quote_decimals)
        details.add(precision)
        layout.addWidget(details)
        actions = QHBoxLayout()
        run = QPushButton("Run")
        run.setObjectName("PrimaryButton")
        run.clicked.connect(self._emit_run)
        actions.addWidget(run)
        self.compare_button = QPushButton("Compare")
        self.compare_button.setObjectName("SecondaryButton")
        self.compare_button.clicked.connect(self._emit_compare)
        self.compare_button.setVisible(kind == "backtests")
        actions.addWidget(self.compare_button)
        quality = QPushButton("Check quality")
        quality.setObjectName("SecondaryButton")
        quality.clicked.connect(self._emit_quality)
        actions.addWidget(quality)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.quality = QLabel("")
        self.quality.setObjectName("Notice")
        self.quality.setWordWrap(True)
        layout.addWidget(self.quality)
        self.equity = SeriesChart("No stored equity curve.")
        self.drawdown = SeriesChart("No stored drawdown curve.")
        layout.addWidget(QLabel("Equity"))
        layout.addWidget(self.equity)
        layout.addWidget(QLabel("Drawdown"))
        layout.addWidget(self.drawdown)
        self.trades = _table(("Side", "State", "Quantity", "Fill", "Shield", "Reason"))
        self.comparisons = _table(("Strategy", "Net", "Trades", "Max drawdown"))
        layout.addWidget(QLabel("Trades"))
        layout.addWidget(self.trades)
        layout.addWidget(QLabel("Comparisons"))
        layout.addWidget(self.comparisons)
        self.paper_box = QWidget()
        paper_layout = QVBoxLayout(self.paper_box)
        paper_layout.setContentsMargins(0, 0, 0, 0)
        self.paper_notice = QLabel(
            "Manual paper entry is available in PAPER mode. "
            "Candle volume is not accepted as depth. Live trading stays locked."
            if paper_enabled
            else "Read-only mode does not submit a paper order. Live trading stays locked."
        )
        self.paper_notice.setObjectName("Notice")
        self.paper_notice.setWordWrap(True)
        paper_form = QFormLayout()
        self.order_strategy = QLineEdit()
        self.order_strategy.setPlaceholderText("Running strategy id")
        self.order_side = QComboBox()
        self.order_side.addItems(["BUY", "SELL"])
        self.order_quantity = QLineEdit()
        self.order_quantity.setPlaceholderText("Quantity")
        self.order_key = QLineEdit()
        self.order_key.setPlaceholderText("Idempotency key")
        self.order_time = QLineEdit()
        self.order_time.setPlaceholderText("Bar time, ISO-8601 with timezone")
        self.order_close = QLineEdit()
        self.order_close.setPlaceholderText("Close, a mark and not a fill")
        self.base_reserve = QLineEdit()
        self.quote_reserve = QLineEdit()
        self.bid = QLineEdit()
        self.ask = QLineEdit()
        self.bid_size = QLineEdit()
        self.ask_size = QLineEdit()
        paper_form.addRow("Strategy", self.order_strategy)
        paper_form.addRow("Side", self.order_side)
        paper_form.addRow("Quantity", self.order_quantity)
        paper_form.addRow("Idempotency", self.order_key)
        paper_form.addRow("Bar time", self.order_time)
        paper_form.addRow("Close mark", self.order_close)
        paper_form.addRow("Base reserve", self.base_reserve)
        paper_form.addRow("Quote reserve", self.quote_reserve)
        paper_form.addRow("Bid", self.bid)
        paper_form.addRow("Ask", self.ask)
        paper_form.addRow("Bid size", self.bid_size)
        paper_form.addRow("Ask size", self.ask_size)
        self.paper_button = QPushButton("Submit paper order")
        self.paper_button.setObjectName("PrimaryButton")
        self.paper_button.setEnabled(paper_enabled and kind == "paper")
        self.paper_button.clicked.connect(self._emit_paper)
        paper_layout.addWidget(self.paper_notice)
        paper_layout.addLayout(paper_form)
        paper_layout.addWidget(self.paper_button)
        self.paper_box.setVisible(kind == "paper")
        layout.addWidget(self.paper_box)
        self.audits = _table(("Time", "Strategy", "Action", "Reason", "Strength", "Threshold"))
        self.audits.setVisible(kind == "paper")
        if kind == "paper":
            layout.addWidget(QLabel("Audit"))
            layout.addWidget(self.audits)
        layout.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll)

    def show_message(self, text: str) -> None:
        self.notice.setText(text)

    def show_summary(self, text: str) -> None:
        self.notice.setText(text)

    def show_catalog(self, datasets: object, runs: object) -> None:
        current = self.dataset.currentData()
        self.dataset.clear()
        count = 0
        if isinstance(datasets, list):
            for item in datasets:
                if not isinstance(item, dict):
                    continue
                dataset_id = item.get("dataset_id")
                name = item.get("name")
                if isinstance(dataset_id, str) and isinstance(name, str):
                    self.dataset.addItem(f"{name} ({dataset_id})", dataset_id)
                    count += 1
        if isinstance(current, str):
            index = self.dataset.findData(current)
            if index >= 0:
                self.dataset.setCurrentIndex(index)
        if count == 0:
            self.notice.setText("No dataset is stored. Candle volume is not executable depth.")
        else:
            self.notice.setText(f"{count} stored datasets. Candle volume is not executable depth.")
        if isinstance(runs, list) and runs and isinstance(runs[-1], dict):
            self.show_report(runs[-1])

    def show_quality(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        self.quality.setText(
            "Bars {bars}. Gaps {gaps}. Outliers {outliers}. Stale {stale}. "
            "Fillable {fillable} ({reserve} reserve, {depth} depth). "
            "Volume-only {volume}. Candle volume is not executable depth.".format(
                bars=payload.get("bar_count", 0),
                gaps=payload.get("gap_count", 0),
                outliers=payload.get("outlier_count", 0),
                stale=payload.get("stale", False),
                fillable=payload.get("fillable_bar_count", 0),
                reserve=payload.get("reserve_bar_count", 0),
                depth=payload.get("depth_bar_count", 0),
                volume=payload.get("volume_only_bar_count", 0),
            )
        )

    def show_report(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        self.equity.set_points(_points(payload.get("equity_curve")))
        self.drawdown.set_points(_points(payload.get("drawdown_curve")))
        orders = payload.get("orders")
        rows: list[tuple[str, ...]] = []
        if isinstance(orders, list):
            for item in orders:
                if not isinstance(item, dict):
                    continue
                rows.append(
                    (
                        str(item.get("side", "")),
                        str(item.get("state", "")),
                        str(item.get("quantity", "")),
                        str(item.get("fill_price", "")),
                        str(item.get("shield_decision", "")),
                        str(item.get("reason", "")),
                    )
                )
        _fill(self.trades, rows)
        strategies = payload.get("strategies")
        compared: list[tuple[str, ...]] = []
        if isinstance(strategies, list):
            for item in strategies:
                if not isinstance(item, dict):
                    continue
                compared.append(
                    (
                        str(item.get("name", item.get("strategy_id", ""))),
                        str(item.get("net_profit", "")),
                        str(item.get("trade_count", "")),
                        str(item.get("max_drawdown", "")),
                    )
                )
        _fill(self.comparisons, compared)
        performance = payload.get("performance")
        if isinstance(performance, dict):
            self.notice.setText(
                f"Stored {payload.get('kind', 'simulation')} {payload.get('strategy_id', '')}. "
                f"Net {performance.get('net_profit')}. "
                f"Max drawdown {performance.get('max_drawdown')}. "
                "Parameters are not deployed. Live trading stays locked."
            )

    def show_audits(self, rows: object) -> None:
        parsed: list[tuple[str, ...]] = []
        if isinstance(rows, list):
            for item in rows:
                if not isinstance(item, dict):
                    continue
                parsed.append(
                    (
                        str(item.get("created_at", "")),
                        str(item.get("strategy_id", "")),
                        str(item.get("action", "")),
                        str(item.get("reason", "")),
                        str(item.get("signal_strength", "")),
                        str(item.get("threshold", "")),
                    )
                )
        _fill(self.audits, parsed)

    def _browse(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Import a dataset",
            "",
            "Market files (*.csv *.parquet)",
        )
        if path:
            self.import_path.setText(path)

    def _emit_import(self) -> None:
        self.import_requested.emit(
            {
                "path": self.import_path.text().strip(),
                "format": self.import_format.currentText(),
                "dataset_id": self.dataset_id.text().strip(),
                "name": self.dataset_name.text().strip(),
                "selection_note": self.selection_note.text().strip(),
            }
        )

    def _emit_collect(self) -> None:
        self.collect_requested.emit(
            {
                "source": self.collect_source.currentData(),
                "dataset_id": self.dataset_id.text().strip(),
                "name": self.dataset_name.text().strip(),
                "selection_note": self.selection_note.text().strip(),
                "mint": self.collect_mint.text().strip(),
                "symbol": self.collect_symbol.text().strip() or "TOKEN",
                "resolution": self.resolution.currentText(),
            }
        )

    def _emit_quality(self) -> None:
        dataset_id = self.dataset.currentData()
        if not isinstance(dataset_id, str) or not dataset_id:
            dataset_id = self.dataset_id.text().strip()
        self.quality_requested.emit({"dataset_id": dataset_id})

    def _emit_run(self) -> None:
        self.run_requested.emit(self._run_body())

    def _emit_compare(self) -> None:
        body = self._run_body()
        body["strategies"] = ["momentum", "breakout", "signal-follow"]
        self.compare_requested.emit(body)

    def _emit_paper(self) -> None:
        if not self.paper_enabled:
            self.show_message("Read-only mode does not submit a paper order.")
            return
        mint = self.instrument_mint.text().strip() or self.collect_mint.text().strip()
        self.paper_requested.emit(
            {
                "strategy_id": self.order_strategy.text().strip(),
                "instrument": self._instrument(mint),
                "side": self.order_side.currentText(),
                "quantity": self.order_quantity.text().strip(),
                "idempotency_key": self.order_key.text().strip(),
                "bar": {
                    "mint": mint,
                    "symbol": self.instrument_symbol.text().strip() or "TOKEN",
                    "observed_at": self.order_time.text().strip(),
                    "source": "manual_paper",
                    "close": _blank(self.order_close.text()),
                    "base_reserve": _blank(self.base_reserve.text()),
                    "quote_reserve": _blank(self.quote_reserve.text()),
                    "bid": _blank(self.bid.text()),
                    "ask": _blank(self.ask.text()),
                    "bid_size": _blank(self.bid_size.text()),
                    "ask_size": _blank(self.ask_size.text()),
                },
            }
        )

    def _run_body(self) -> dict[str, object]:
        dataset_id = self.dataset.currentData()
        if not isinstance(dataset_id, str) or not dataset_id:
            dataset_id = self.dataset_id.text().strip()
        mint = self.instrument_mint.text().strip()
        return {
            "dataset_id": dataset_id,
            "strategy": self.strategy.currentText(),
            "parameters": {
                "lookback": self.lookback.text().strip(),
                "entry_return": self.entry_return.text().strip(),
                "stop_fraction": self.stop_fraction.text().strip(),
            },
            "starting_equity": self.starting_equity.text().strip(),
            "fee_fixed": "0",
            "fee_rate": "0.001",
            "instruments": [self._instrument(mint)],
        }

    def _instrument(self, mint: str) -> dict[str, object]:
        return {
            "mint": mint,
            "symbol": self.instrument_symbol.text().strip() or "TOKEN",
            "size_decimals": _int(self.size_decimals.text(), 6),
            "price_decimals": _int(self.price_decimals.text(), 6),
            "quote_symbol": self.quote_symbol.text().strip() or "SOL",
            "quote_decimals": _int(self.quote_decimals.text(), 9),
        }


def _table(headers: tuple[str, ...]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.verticalHeader().setVisible(False)
    table.setShowGrid(False)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.setMinimumHeight(120)
    return table


def _fill(table: QTableWidget, rows: list[tuple[str, ...]]) -> None:
    table.setRowCount(len(rows))
    for row_index, values in enumerate(rows):
        for column, value in enumerate(values):
            table.setItem(row_index, column, QTableWidgetItem(value))


def _points(value: object) -> list[Decimal]:
    if not isinstance(value, list):
        return []
    points: list[Decimal] = []
    for item in value:
        if not isinstance(item, str):
            continue
        try:
            points.append(Decimal(item))
        except InvalidOperation:
            continue
    return points


def _blank(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def _int(value: str, default: int) -> int:
    stripped = value.strip()
    if stripped.isdecimal():
        return int(stripped)
    return default
