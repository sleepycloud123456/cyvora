"""Main window shell."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from apps.desktop.navigation import DASHBOARD, PAGES, SYSTEM_HEALTH
from apps.desktop.pages.dashboard_page import DashboardPage
from apps.desktop.pages.health_page import HealthPage
from apps.desktop.pages.placeholder_page import PlaceholderPage
from apps.desktop.pages.radar_page import RadarPage
from apps.desktop.pages.trading_page import TradingPage
from apps.desktop.services.probe import StatusProbe
from apps.desktop.services.radar_worker import RadarCycleWorker, RadarLoadWorker, WatchWorker
from apps.desktop.services.trading_worker import TradingLoadWorker
from config.settings import Settings
from domain.enums import ExecutionMode
from domain.status import StatusSnapshot
from domain.trading import TradingSnapshot
from intelligence.schedule import next_delay_seconds
from intelligence.store import CycleSnapshot


class MainWindow(QMainWindow):
    """Navigation shell for the Phase 1 terminal."""

    def __init__(self, settings: Settings, *, start_probe: bool = True) -> None:
        super().__init__()
        self._settings = settings
        self._closing = False
        self._probe: StatusProbe | None = None
        self._radar_load: RadarLoadWorker | None = None
        self._radar_cycle: RadarCycleWorker | None = None
        self._watch_worker: WatchWorker | None = None
        self._trading_load: TradingLoadWorker | None = None
        self._cycle_generation = 0
        self.setWindowTitle("CYVORA Terminal")
        self.setMinimumSize(1100, 720)
        self._build()
        self._show_page(DASHBOARD)
        if start_probe:
            self.start_probe()
            self._load_radar()
        else:
            self.dashboard.set_idle()
            self.health.set_idle()
            if self._settings.database_url is None:
                self._radar_message("Radar storage is not configured. No tokens are shown.")

    def _build(self) -> None:
        shell = QWidget()
        shell.setObjectName("Shell")
        root = QHBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        content = self._build_content()
        sidebar = self._build_sidebar()
        root.addWidget(sidebar)
        root.addWidget(content, stretch=1)
        self.setCentralWidget(shell)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(260)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(6)

        brand = QLabel("CYVORA")
        brand.setObjectName("BrandTitle")
        slogan = QLabel("TRADE BEYOND LIMITS.")
        slogan.setObjectName("Slogan")
        self.mode_badge = QLabel(self._mode_text())
        self.mode_badge.setObjectName("ModeBadge")
        self.mode_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lock = QLabel("Live trading is locked")
        lock.setObjectName("LockNote")

        self.navigation = QListWidget()
        self.navigation.setObjectName("Navigation")
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.navigation.setFrameShape(QFrame.Shape.NoFrame)
        for name in PAGES:
            QListWidgetItem(name, self.navigation)
        self.navigation.currentTextChanged.connect(self._show_page)
        self.navigation.setCurrentRow(0)

        layout.addWidget(brand)
        layout.addWidget(slogan)
        layout.addSpacing(10)
        layout.addWidget(self.mode_badge)
        layout.addWidget(lock)
        layout.addSpacing(8)
        layout.addWidget(self.navigation, stretch=1)
        return sidebar

    def _build_content(self) -> QWidget:
        content = QFrame()
        content.setObjectName("Content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(8)
        self.page_title = QLabel(DASHBOARD)
        self.page_title.setObjectName("PageTitle")
        self.stack = QStackedWidget()
        self.dashboard = DashboardPage()
        self.health = HealthPage(self._settings)
        self.placeholder = PlaceholderPage()
        self.scanner = RadarPage("scanner")
        self.trending = RadarPage("trending")
        self.launches = RadarPage("launches")
        self.analysis = RadarPage("analysis")
        self.smart_money = RadarPage("smart")
        self.whales = RadarPage("whale")
        self.positions = TradingPage("positions")
        self.orders = TradingPage("orders")
        self.strategies = TradingPage("strategies")
        self.scanner.run_button.clicked.connect(self._start_cycle)
        self.scanner.continuous.toggled.connect(self._continuous_toggled)
        self.scanner.watch_add.connect(self._add_watch)
        self.scanner.watch_remove.connect(self._remove_watch)
        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.health)
        self.stack.addWidget(self.placeholder)
        for page in self._radar_pages():
            self.stack.addWidget(page)
        for trading_page in (self.positions, self.orders, self.strategies):
            self.stack.addWidget(trading_page)
        layout.addWidget(self.page_title)
        layout.addWidget(self.stack, stretch=1)
        return content

    def _mode_text(self) -> str:
        if self._settings.execution_mode is ExecutionMode.PAPER:
            return "PAPER"
        return "READ-ONLY"

    def _show_page(self, name: str) -> None:
        if not name:
            return
        self.page_title.setText(name)
        if name == DASHBOARD:
            self.stack.setCurrentWidget(self.dashboard)
            return
        if name == SYSTEM_HEALTH:
            self.stack.setCurrentWidget(self.health)
            return
        radar = {
            "Live Scanner": self.scanner,
            "Trending Tokens": self.trending,
            "New Launches": self.launches,
            "Token Analysis": self.analysis,
            "Smart Money": self.smart_money,
            "Whale Tracker": self.whales,
        }.get(name)
        if radar is not None:
            self.stack.setCurrentWidget(radar)
            return
        trading = {
            "Open Positions": self.positions,
            "Trade History": self.orders,
            "Strategies": self.strategies,
        }.get(name)
        if trading is not None:
            self.stack.setCurrentWidget(trading)
            self._load_trading()
            return
        self.placeholder.show_page(name)
        self.stack.setCurrentWidget(self.placeholder)

    def start_probe(self) -> None:
        self.dashboard.set_checking()
        self.health.set_checking()
        self._probe = StatusProbe(self._settings)
        self._probe.snapshot_ready.connect(self.apply_snapshot)
        self._probe.failed.connect(self._show_probe_failure)
        self._probe.start()

    def apply_snapshot(self, snapshot: object) -> None:
        if self._closing or not isinstance(snapshot, StatusSnapshot):
            return
        self.dashboard.apply_snapshot(snapshot)
        self.health.apply_snapshot(snapshot)

    def _show_probe_failure(self, message: str) -> None:
        if self._closing:
            return
        self.dashboard.show_probe_failure(message)
        self.health.show_probe_failure(message)

    def shutdown(self) -> None:
        self._closing = True
        self._cycle_generation += 1
        probe = self._probe
        if probe is not None and probe.isRunning():
            probe.requestInterruption()
            probe.wait(4000)
        for worker in (
            self._radar_load,
            self._radar_cycle,
            self._watch_worker,
            self._trading_load,
        ):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(4000)

    def _load_trading(self) -> None:
        if not self._settings.database_url:
            message = "Trading storage is not configured. No simulated orders are shown."
            for page in (self.positions, self.orders, self.strategies):
                page.show_message(message)
            return
        if self._trading_load is not None and self._trading_load.isRunning():
            return
        self._trading_load = TradingLoadWorker(self._settings)
        self._trading_load.loaded.connect(self._apply_trading)
        self._trading_load.failed.connect(self._trading_message)
        self._trading_load.start()

    def _apply_trading(self, snapshot: object) -> None:
        if self._closing or not isinstance(snapshot, TradingSnapshot):
            return
        for page in (self.positions, self.orders, self.strategies):
            page.show_snapshot(snapshot)

    def _trading_message(self, text: str) -> None:
        if self._closing:
            return
        for page in (self.positions, self.orders, self.strategies):
            page.show_message(text)

    def _radar_pages(self) -> tuple[RadarPage, ...]:
        return (
            self.scanner,
            self.trending,
            self.launches,
            self.analysis,
            self.smart_money,
            self.whales,
        )

    def _radar_message(self, text: str) -> None:
        for page in self._radar_pages():
            page.show_message(text)

    def _load_radar(self) -> None:
        if not self._settings.database_url:
            self._radar_message("Radar storage is not configured. No tokens are shown.")
            return
        self._radar_load = RadarLoadWorker(self._settings)
        self._radar_load.loaded.connect(self._apply_radar)
        self._radar_load.failed.connect(self._radar_message)
        self._radar_load.start()

    def _apply_radar(self, snapshot: object) -> None:
        if self._closing:
            return
        if snapshot is not None and not isinstance(snapshot, CycleSnapshot):
            return
        for page in self._radar_pages():
            page.show_snapshot(snapshot if isinstance(snapshot, CycleSnapshot) else None)

    def _start_cycle(self, generation: int | None = None) -> None:
        if self._closing:
            return
        if generation is not None and generation != self._cycle_generation:
            return
        if not self._settings.database_url:
            self.scanner.show_message("Radar storage is not configured. The cycle was not started.")
            return
        if self._settings.gmgn_api_key is None:
            self.scanner.show_message("GMGN_API_KEY is not set. The cycle was not started.")
            return
        if self._radar_cycle is not None and self._radar_cycle.isRunning():
            return
        for page in self._radar_pages():
            page.set_running(True)
        self._radar_cycle = RadarCycleWorker(self._settings)
        self._radar_cycle.finished_ok.connect(self._cycle_finished)
        self._radar_cycle.failed.connect(self._cycle_failed)
        self._radar_cycle.start()

    def _cycle_finished(self, message: str) -> None:
        if self._closing:
            return
        for page in self._radar_pages():
            page.set_running(False)
        self.scanner.show_message(message)
        self._load_radar()
        self._schedule_next()

    def _cycle_failed(self, message: str) -> None:
        if self._closing:
            return
        for page in self._radar_pages():
            page.set_running(False)
        self.scanner.show_message(message)
        self._load_radar()
        self._schedule_next()

    def _schedule_next(self) -> None:
        worker = self._radar_cycle
        if worker is None or worker.last_result is None or not self.scanner.continuous.isChecked():
            return
        delay = next_delay_seconds(self._settings.radar_scan_interval_seconds, worker.last_result)
        generation = self._cycle_generation
        QTimer.singleShot(delay * 1000, lambda: self._start_cycle(generation))

    def _continuous_toggled(self, checked: bool) -> None:
        if not checked:
            self._cycle_generation += 1

    def _add_watch(self, chain: str, address: str, symbol: str) -> None:
        self._change_watch("add", chain, address, symbol)

    def _remove_watch(self, chain: str, address: str) -> None:
        self._change_watch("remove", chain, address, "")

    def _change_watch(self, action: str, chain: str, address: str, symbol: str) -> None:
        if not self._settings.database_url:
            self.scanner.show_message("Radar storage is not configured.")
            return
        if self._watch_worker is not None and self._watch_worker.isRunning():
            return
        self._watch_worker = WatchWorker(self._settings, action, chain, address, symbol)
        self._watch_worker.finished_ok.connect(self._load_radar)
        self._watch_worker.failed.connect(self.scanner.show_message)
        self._watch_worker.start()
