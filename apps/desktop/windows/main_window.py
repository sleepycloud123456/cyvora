"""Main window shell."""

from __future__ import annotations

from PySide6.QtCore import Qt
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
from apps.desktop.services.probe import StatusProbe
from config.settings import Settings
from domain.enums import ExecutionMode
from domain.status import StatusSnapshot


class MainWindow(QMainWindow):
    """Navigation shell for the Phase 1 terminal."""

    def __init__(self, settings: Settings, *, start_probe: bool = True) -> None:
        super().__init__()
        self._settings = settings
        self._closing = False
        self._probe: StatusProbe | None = None
        self.setWindowTitle("CYVORA Terminal")
        self.setMinimumSize(1100, 720)
        self._build()
        self._show_page(DASHBOARD)
        if start_probe:
            self.start_probe()
        else:
            self.dashboard.set_idle()
            self.health.set_idle()

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
        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.health)
        self.stack.addWidget(self.placeholder)
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
        probe = self._probe
        if probe is not None and probe.isRunning():
            probe.requestInterruption()
            probe.wait(4000)
