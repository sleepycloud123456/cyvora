"""Desktop application helpers."""

from __future__ import annotations

from pathlib import Path

from apps.desktop.windows.main_window import MainWindow
from config.settings import Settings, get_settings


def load_stylesheet() -> str:
    """Load the shared CYVORA theme."""

    path = Path(__file__).resolve().parent / "themes" / "cyvora.qss"
    return path.read_text(encoding="utf-8")


def create_window(settings: Settings | None = None, *, start_probe: bool = True) -> MainWindow:
    """Build the main window without starting the Qt event loop."""

    return MainWindow(settings=settings or get_settings(), start_probe=start_probe)
