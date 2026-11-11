"""The Phase 1 terminal shell."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt

from apps.desktop.app import load_stylesheet
from apps.desktop.navigation import PAGES
from apps.desktop.windows.main_window import MainWindow
from config.settings import Settings
from domain.enums import ExecutionMode
from domain.status import ComponentStatus, StatusSnapshot


def test_theme_uses_the_shared_accent() -> None:
    stylesheet = load_stylesheet()
    assert "#22D3EE" in stylesheet
    assert "#2DD4BF" in stylesheet
    assert "#070B14" in stylesheet


def test_navigation_lists_the_planned_pages() -> None:
    assert len(PAGES) == 19
    assert PAGES[0] == "Dashboard"
    assert PAGES[-1] == "System Health"


def test_shell_labels_placeholders(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = MainWindow(Settings(_env_file=None), start_probe=False)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    assert window.windowTitle() == "CYVORA Terminal"
    assert window.mode_badge.text() == "READ-ONLY"
    assert "not available" in window.dashboard.notice.text()
    matches = window.navigation.findItems("Portfolio", Qt.MatchFlag.MatchExactly)
    assert matches
    window.navigation.setCurrentItem(matches[0])
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.placeholder)
    assert window.page_title.text() == "Portfolio"
    assert "Placeholder" in window.placeholder.body.text()
    assert "Phase 5" in window.placeholder.body.text()
    risk_matches = window.navigation.findItems("Risk Management", Qt.MatchFlag.MatchExactly)
    window.navigation.setCurrentItem(risk_matches[0])
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.risk)
    assert "not configured" in window.risk.notice.text()
    strategy_matches = window.navigation.findItems("Strategies", Qt.MatchFlag.MatchExactly)
    window.navigation.setCurrentItem(strategy_matches[0])
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.strategies)
    assert "not configured" in window.strategies.notice.text()
    assert window.strategies.table.rowCount() == 0


def test_navigation_stays_responsive(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = MainWindow(Settings(_env_file=None), start_probe=False)
    qtbot.addWidget(window)
    window.show()
    started = time.perf_counter()
    for name in ("Dashboard", "System Health", "Portfolio", "Dashboard"):
        matches = window.navigation.findItems(name, Qt.MatchFlag.MatchExactly)
        window.navigation.setCurrentItem(matches[0])
        qtbot.wait(1)
    assert time.perf_counter() - started < 2


def test_snapshot_updates_cards_without_market_data(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = MainWindow(
        Settings(_env_file=None, execution_mode=ExecutionMode.PAPER),
        start_probe=False,
    )
    qtbot.addWidget(window)
    snapshot = StatusSnapshot(
        app_name="CYVORA",
        version="0.2.0",
        phase="2",
        environment="local",
        execution_mode="PAPER",
        live_trading_enabled=False,
        application=ComponentStatus("running", "CYVORA 0.2.0 phase 2"),
        database=ComponentStatus("not_configured", "CYVORA_DATABASE_URL is not set."),
        backend=ComponentStatus("offline", "The CYVORA API is not accepting connections."),
        gmgn=ComponentStatus("not_configured", "GMGN_API_KEY is not set."),
    )
    window.apply_snapshot(snapshot)
    assert window.mode_badge.text() == "PAPER"
    assert window.dashboard.database_card.state_label.text() == "not_configured"
    assert window.dashboard.backend_card.state_label.text() == "offline"
    assert "0.2.0" in window.dashboard.application_card.detail_label.text()
    assert window.dashboard.gmgn_card.state_label.text() == "not_configured"
    theme = Path(__file__).resolve().parents[2] / "apps" / "desktop" / "themes" / "cyvora.qss"
    assert theme.is_file()
