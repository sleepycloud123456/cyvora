"""CYVORA Terminal entry point."""

from __future__ import annotations

import sys
import time

from PySide6.QtWidgets import QApplication

from apps.desktop.app import create_window, load_stylesheet
from config.settings import Settings, get_settings


def _run(argv: list[str], settings: Settings) -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("CYVORA Terminal")
    application.setOrganizationName("CYVORA")
    application.setStyleSheet(load_stylesheet())
    smoke = "--smoke" in argv
    window = create_window(settings, start_probe=smoke or "--no-probe" not in argv)
    window.show()
    if not smoke:
        code = application.exec()
        window.shutdown()
        return int(code)

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        application.processEvents()
        if window.dashboard.backend_card.state_label.text() != "Checking...":
            break
        time.sleep(0.05)
    application.processEvents()
    visible = window.isVisible()
    titled = window.windowTitle() == "CYVORA Terminal"
    mode_ok = window.mode_badge.text() in {"READ-ONLY", "PAPER"}
    notice_ok = "not available" in window.dashboard.notice.text()
    checked = window.dashboard.backend_card.state_label.text() != "Checking..."
    window.shutdown()
    window.close()
    application.processEvents()
    if visible and titled and mode_ok and notice_ok and checked:
        print(
            "CYVORA_DESKTOP_SMOKE_OK "
            f"python={sys.version.split()[0]} "
            f"mode={window.mode_badge.text()} "
            f"database={window.dashboard.database_card.state_label.text()} "
            f"backend={window.dashboard.backend_card.state_label.text()} "
            f"gmgn={window.dashboard.gmgn_card.state_label.text()}"
        )
        return 0
    print("CYVORA_DESKTOP_SMOKE_FAIL")
    return 1


def main(argv: list[str] | None = None) -> None:
    """Launch the terminal. ``--smoke`` shows the window, checks it, and exits."""

    args = list(sys.argv[1:] if argv is None else argv)
    raise SystemExit(_run(args, get_settings()))


if __name__ == "__main__":
    main()
