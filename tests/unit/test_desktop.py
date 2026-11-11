"""The Phase 1 terminal shell."""

from __future__ import annotations

import time
from pathlib import Path

from apps.desktop.app import load_stylesheet
from apps.desktop.components.hologram import Hologram
from apps.desktop.navigation import CATALOG, HIDDEN_PAGES, PAGES
from apps.desktop.windows.main_window import MainWindow
from config.settings import Settings
from domain.enums import ExecutionMode
from domain.status import ComponentStatus, StatusSnapshot


def test_theme_uses_the_shared_accent() -> None:
    stylesheet = load_stylesheet()
    assert "#000000" in stylesheet
    assert "#C084FC" in stylesheet
    assert "#A855F7" in stylesheet


def test_navigation_lists_the_planned_pages() -> None:
    assert PAGES == (
        "Dashboard",
        "Open Positions",
        "Trade History",
        "Paper Trading",
        "Strategies",
        "Backtesting",
        "Risk Management",
        "Analytics",
        "Notifications",
        "System Health",
    )
    hidden = {
        "Live Scanner",
        "Trending Tokens",
        "New Launches",
        "Token Analysis",
        "Smart Money",
        "Whale Tracker",
        "Portfolio",
        "CYVORA Intelligence",
        "Settings",
    }
    assert hidden == set(HIDDEN_PAGES)
    assert {item.name for item in CATALOG} == set(PAGES) | hidden
    assert all(item.shown for item in CATALOG if item.name in PAGES)


def test_shell_labels_placeholders(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = MainWindow(Settings(_env_file=None), start_probe=False)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    assert window.windowTitle() == "CYVORA Terminal"
    assert window.mode_badge.text() == "READ-ONLY"
    assert "Live trading is locked" in window.mode_badge.toolTip()
    assert window.slogan.text() == "TRADE BEYOND LIMITS."
    assert "not available" in window.dashboard.notice.text()
    assert window.navigation.names() == PAGES
    assert window.navigation.button("Dashboard").toolTip() == "Dashboard"
    for hidden in ("Portfolio", "Settings", "Live Scanner", "CYVORA Intelligence"):
        assert hidden not in window.navigation.names()
    window.show_page("Portfolio")
    assert window.stack.currentWidget() is window.portfolio
    assert window.page_title.text() == "Portfolio"
    assert "not configured" in window.portfolio.notice.text()
    assert "not available" in window.dashboard.notice.text()
    window.show_page("Settings")
    assert window.stack.currentWidget() is window.settings_page
    assert "Live trading is locked" in window.settings_page.live_lock.text()
    assert window.settings_page.kill_engage.text() == "Engage kill switch"
    assert window.settings_page.kill_release.text() == "Release kill switch"
    assert window.settings_page.telegram.isEnabled() is False
    assert window.settings_page.telegram.isChecked() is False
    assert window.settings_page.motion.isChecked() is True
    window.placeholder.show_page("Unknown")
    assert "Placeholder" in window.placeholder.body.text()
    window.navigation.button("Risk Management").click()
    assert window.stack.currentWidget() is window.risk
    assert "not configured" in window.risk.notice.text()
    window.navigation.button("Backtesting").click()
    assert window.stack.currentWidget() is window.backtests
    assert "not configured" in window.backtests.notice.text()
    window.navigation.button("Strategies").click()
    assert window.stack.currentWidget() is window.strategies
    assert "not configured" in window.strategies.notice.text()
    assert window.strategies.table.rowCount() == 0


def test_navigation_stays_responsive(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = MainWindow(Settings(_env_file=None), start_probe=False)
    qtbot.addWidget(window)
    window.show()
    started = time.perf_counter()
    for name in ("Dashboard", "System Health", "Analytics", "Dashboard"):
        window.navigation.button(name).click()
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


def test_motion_flag_stops_the_hologram(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = MainWindow(Settings(_env_file=None, ui_animations=False), start_probe=False)
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(30)
    assert window.dashboard.hologram.animating() is False
    assert window.settings_page.motion.isChecked() is False
    window.settings_page.motion.setChecked(True)
    assert window.dashboard.hologram.animating() is True
    window.settings_page.motion.setChecked(False)
    assert window.dashboard.hologram.animating() is False


def test_hologram_frame_uses_purple(qtbot) -> None:  # type: ignore[no-untyped-def]
    hologram = Hologram(animated=False)
    qtbot.addWidget(hologram)
    hologram.resize(300, 360)
    hologram.show()
    qtbot.waitExposed(hologram)
    image = hologram.grab().toImage()
    assert image.width() == 300
    found = False
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            color = image.pixelColor(x, y)
            if color.red() > 70 and color.blue() > color.green() + 20 and color.blue() > 80:
                found = True
                break
        if found:
            break
    assert found
