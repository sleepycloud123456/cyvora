"""Pause, resume, and the kill switch. The prompts match the stored checks.

These buttons call the existing paper actions. None of them enables live trading,
submits an order, or skips a confirmation.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QWidget

PAUSE_TITLE = "Pause new entries"
PAUSE_PROMPT = (
    "Pause new paper entries? This does not submit an order and does not enable live trading."
)
RESUME_TITLE = "Resume paper entries"
RESUME_PROMPT = "Allow Shield to evaluate new paper entries again? Live trading stays locked."
ENGAGE_TITLE = "Engage kill switch"
ENGAGE_PROMPT = (
    "Block new operator paper orders? This does not submit an order, "
    "does not flatten a position, and does not enable live trading. "
    "Resume paper entries does not release this switch."
)
RELEASE_TITLE = "Release kill switch"
RELEASE_PROMPT = (
    "Allow Shield to evaluate new operator paper orders again? Live trading stays locked."
)


class EmergencyControls(QWidget):
    """The four paper-only controls, full size or compact for the header."""

    pause_requested = Signal()
    resume_requested = Signal()
    kill_engage_requested = Signal()
    kill_release_requested = Signal()

    def __init__(self, *, compact: bool = False) -> None:
        super().__init__()
        self.setObjectName("EmergencyControls")
        danger = "CompactDanger" if compact else "DangerButton"
        secondary = "CompactSecondary" if compact else "SecondaryButton"
        self.pause = QPushButton("Pause" if compact else "Pause new entries")
        self.resume = QPushButton("Resume" if compact else "Resume paper entries")
        self.kill_engage = QPushButton("Kill" if compact else "Engage kill switch")
        self.kill_release = QPushButton("Release" if compact else "Release kill switch")
        self.pause.setObjectName(danger)
        self.kill_engage.setObjectName(danger)
        self.resume.setObjectName(secondary)
        self.kill_release.setObjectName(secondary)
        self.pause.setToolTip(PAUSE_TITLE)
        self.resume.setToolTip(RESUME_TITLE)
        self.kill_engage.setToolTip(ENGAGE_TITLE)
        self.kill_release.setToolTip(RELEASE_TITLE)
        self.pause.clicked.connect(self._pause)
        self.resume.clicked.connect(self._resume)
        self.kill_engage.clicked.connect(self._engage_kill)
        self.kill_release.clicked.connect(self._release_kill)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8 if compact else 12)
        layout.addWidget(self.pause)
        layout.addWidget(self.resume)
        layout.addWidget(self.kill_engage)
        layout.addWidget(self.kill_release)
        if not compact:
            layout.addStretch(1)

    def _pause(self) -> None:
        if _confirm(self, PAUSE_TITLE, PAUSE_PROMPT):
            self.pause_requested.emit()

    def _resume(self) -> None:
        if _confirm(self, RESUME_TITLE, RESUME_PROMPT):
            self.resume_requested.emit()

    def _engage_kill(self) -> None:
        if _confirm(self, ENGAGE_TITLE, ENGAGE_PROMPT):
            self.kill_engage_requested.emit()

    def _release_kill(self) -> None:
        if _confirm(self, RELEASE_TITLE, RELEASE_PROMPT):
            self.kill_release_requested.emit()


def _confirm(parent: QWidget, title: str, prompt: str) -> bool:
    answer = QMessageBox.question(parent, title, prompt)
    return answer == QMessageBox.StandardButton.Yes
