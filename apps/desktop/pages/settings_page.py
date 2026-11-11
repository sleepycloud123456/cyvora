"""Paper settings. No control on this page can enable live trading."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from domain.exceptions import CyvoraError
from domain.terminal import CRITICAL_NOTIFICATIONS, NotificationCategory, TerminalSnapshot
from terminal.profiles import normalize_preferences

_CRITICAL = {item.value for item in CRITICAL_NOTIFICATIONS}


class SettingsPage(QWidget):
    """Show the operating mode and paper-only controls."""

    profile_save = Signal(str, str, object)
    profile_activate = Signal(str)
    preferences_save = Signal(object)
    pause_requested = Signal()
    resume_requested = Signal()
    kill_engage_requested = Signal()
    kill_release_requested = Signal()
    motion_toggled = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)
        self.notice = QLabel("Terminal storage has not been read.")
        self.notice.setObjectName("Notice")
        self.notice.setWordWrap(True)
        self.live_lock = QLabel(
            "Live trading is locked. No control on this page can enable it. "
            "Manual trade override is locked. The kill switch blocks new operator "
            "paper orders and does not sign or submit a transaction."
        )
        self.live_lock.setObjectName("LockNote")
        self.live_lock.setWordWrap(True)
        self.motion = QCheckBox("Animate the terminal")
        self.motion.setToolTip(
            "Session only. CYVORA_UI_ANIMATIONS in the environment sets the startup value. "
            "This does not enable live trading."
        )
        self.motion.toggled.connect(self.motion_toggled.emit)
        self.mode = QLabel("Mode has not been read.")
        self.mode.setObjectName("Notice")
        self.mode.setWordWrap(True)
        self.profile_box = QComboBox()
        self.activate = QPushButton("Select profile")
        self.activate.setObjectName("SecondaryButton")
        self.activate.clicked.connect(self._activate)
        self.profile_id = QLineEdit()
        self.profile_id.setPlaceholderText("New profile id")
        self.profile_name = QLineEdit()
        self.profile_name.setPlaceholderText("Profile name")
        self.profile_strategies = QLineEdit()
        self.profile_strategies.setPlaceholderText("Strategy ids, comma separated")
        self.profile_threshold = QLineEdit()
        self.profile_threshold.setPlaceholderText("Recorded signal threshold, 0 to 1")
        self.save_profile = QPushButton("Store profile")
        self.save_profile.setObjectName("SecondaryButton")
        self.save_profile.clicked.connect(self._save_profile)
        self.profile_note = QLabel(
            "A profile records a name, strategy ids, and an optional signal threshold. "
            "The threshold is not applied to the radar score or to Shield. "
            "It does not change Shield limits, "
            "does not start a strategy, and does not submit an order. "
            "Changing READ_ONLY or PAPER requires the environment setting and a restart."
        )
        self.profile_note.setObjectName("Notice")
        self.profile_note.setWordWrap(True)
        self.pause = QPushButton("Pause new entries")
        self.pause.setObjectName("DangerButton")
        self.pause.clicked.connect(self._pause)
        self.resume = QPushButton("Resume paper entries")
        self.resume.setObjectName("SecondaryButton")
        self.resume.clicked.connect(self._resume)
        self.kill_engage = QPushButton("Engage kill switch")
        self.kill_engage.setObjectName("DangerButton")
        self.kill_engage.clicked.connect(self._engage_kill)
        self.kill_release = QPushButton("Release kill switch")
        self.kill_release.setObjectName("SecondaryButton")
        self.kill_release.clicked.connect(self._release_kill)
        self.categories: dict[str, QCheckBox] = {}
        category_row = QVBoxLayout()
        for category in NotificationCategory:
            box = QCheckBox(category.value)
            box.setChecked(True)
            if category.value in _CRITICAL:
                box.setEnabled(False)
            self.categories[category.value] = box
            category_row.addWidget(box)
        self.quiet_enabled = QCheckBox("Use a UTC quiet period")
        self.quiet_start = QSpinBox()
        self.quiet_start.setRange(0, 1439)
        self.quiet_end = QSpinBox()
        self.quiet_end.setRange(0, 1439)
        self.repeat = QSpinBox()
        self.repeat.setRange(60, 86400)
        self.repeat.setValue(3600)
        self.telegram = QCheckBox("Telegram delivery")
        self.telegram.setChecked(False)
        self.telegram.setEnabled(False)
        self.save_preferences = QPushButton("Store notification settings")
        self.save_preferences.setObjectName("SecondaryButton")
        self.save_preferences.clicked.connect(self._save_preferences)
        profile_buttons = QHBoxLayout()
        profile_buttons.addWidget(self.profile_box)
        profile_buttons.addWidget(self.activate)
        layout.addWidget(self.notice)
        layout.addWidget(self.live_lock)
        layout.addWidget(self.motion)
        layout.addWidget(self.mode)
        layout.addLayout(profile_buttons)
        layout.addWidget(self.profile_id)
        layout.addWidget(self.profile_name)
        layout.addWidget(self.profile_strategies)
        layout.addWidget(self.profile_threshold)
        layout.addWidget(self.save_profile)
        layout.addWidget(self.profile_note)
        layout.addWidget(self.pause)
        layout.addWidget(self.resume)
        layout.addWidget(self.kill_engage)
        layout.addWidget(self.kill_release)
        layout.addLayout(category_row)
        layout.addWidget(self.quiet_enabled)
        layout.addWidget(self.quiet_start)
        layout.addWidget(self.quiet_end)
        layout.addWidget(self.repeat)
        layout.addWidget(self.telegram)
        layout.addWidget(self.save_preferences)
        layout.addStretch(1)

    def show_message(self, text: str) -> None:
        self.notice.setText(text)

    def set_motion(self, enabled: bool) -> None:
        self.motion.blockSignals(True)
        self.motion.setChecked(enabled)
        self.motion.blockSignals(False)

    def show_snapshot(self, snapshot: TerminalSnapshot) -> None:
        settings = snapshot.settings
        self.notice.setText("Paper settings. Live trading stays locked.")
        self.mode.setText(
            f"Mode {settings.execution_mode}. "
            "Paper orders "
            + ("allowed" if settings.paper_orders_allowed else "not stored in read-only mode")
            + ". "
            f"Database {'configured' if settings.database_configured else 'not configured'}. "
            f"GMGN key {'configured' if settings.gmgn_configured else 'not configured'}. "
            f"API {settings.api_host}:{settings.api_port}. "
            f"Entries {'paused' if settings.halt_entries else 'evaluated by Shield'}. "
            f"Breach {'latched' if settings.breach_latched else 'clear'}."
        )
        current = self.profile_box.currentText()
        self.profile_box.clear()
        for profile in snapshot.profiles:
            label = profile.name + (" (selected)" if profile.active else "")
            self.profile_box.addItem(label, profile.profile_id)
        if current:
            index = self.profile_box.findText(current)
            if index >= 0:
                self.profile_box.setCurrentIndex(index)
        enabled = set(snapshot.preferences.enabled_categories)
        for name, box in self.categories.items():
            box.setChecked(name in enabled or name in _CRITICAL)
        start = snapshot.preferences.quiet_start_minute
        end = snapshot.preferences.quiet_end_minute
        self.quiet_enabled.setChecked(start is not None and end is not None)
        if start is not None:
            self.quiet_start.setValue(start)
        if end is not None:
            self.quiet_end.setValue(end)
        self.repeat.setValue(snapshot.preferences.minimum_repeat_seconds)
        self.telegram.setChecked(False)

    def _activate(self) -> None:
        profile_id = self.profile_box.currentData()
        if not isinstance(profile_id, str):
            self.notice.setText("No stored profile is available to select.")
            return
        self.profile_activate.emit(profile_id)

    def _save_profile(self) -> None:
        strategies = tuple(
            part.strip() for part in self.profile_strategies.text().split(",") if part.strip()
        )
        self.profile_save.emit(self.profile_id.text(), self.profile_name.text(), strategies)

    def _pause(self) -> None:
        answer = QMessageBox.question(
            self,
            "Pause new entries",
            "Pause new paper entries? This does not submit an order "
            "and does not enable live trading.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.pause_requested.emit()

    def _resume(self) -> None:
        answer = QMessageBox.question(
            self,
            "Resume paper entries",
            "Allow Shield to evaluate new paper entries again? Live trading stays locked.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.resume_requested.emit()

    def _engage_kill(self) -> None:
        answer = QMessageBox.question(
            self,
            "Engage kill switch",
            "Block new operator paper orders? This does not submit an order, "
            "does not flatten a position, and does not enable live trading. "
            "Resume paper entries does not release this switch.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.kill_engage_requested.emit()

    def _release_kill(self) -> None:
        answer = QMessageBox.question(
            self,
            "Release kill switch",
            "Allow Shield to evaluate new operator paper orders again? Live trading stays locked.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.kill_release_requested.emit()

    def _save_preferences(self) -> None:
        try:
            preferences = normalize_preferences(
                enabled_categories=tuple(
                    name for name, box in self.categories.items() if box.isChecked()
                ),
                quiet_start_minute=self._quiet(self.quiet_start),
                quiet_end_minute=self._quiet(self.quiet_end),
                minimum_repeat_seconds=self.repeat.value(),
                telegram_delivery=False,
                live_trading_enabled=False,
            )
        except CyvoraError as exc:
            self.notice.setText(str(exc))
            return
        self.preferences_save.emit(preferences)

    def _quiet(self, box: QSpinBox) -> int | None:
        if not self.quiet_enabled.isChecked():
            return None
        return box.value()
