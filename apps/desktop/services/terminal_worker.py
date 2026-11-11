"""Load and change terminal records off the UI thread."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import QThread, Signal

from config.settings import Settings
from database.repositories.terminal import PostgresTerminalRepository
from database.repositories.trading import PostgresTradingRepository
from domain.exceptions import CyvoraError
from domain.status import StatusSnapshot
from domain.terminal import NotificationPreferences
from trading.execution.gateway import PaperExecutionGateway
from trading.strategies.manager import StrategyManager


class TerminalLoadWorker(QThread):
    """Read the paper terminal snapshot. The thread does not call GMGN."""

    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, settings: Settings, status: StatusSnapshot | None) -> None:
        super().__init__()
        self._settings = settings
        self._status = status

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            snapshot = PostgresTerminalRepository(self._settings).load(
                self._status, datetime.now(UTC)
            )
        except CyvoraError as exc:
            self.failed.emit(str(exc))
            return
        except Exception:
            self.failed.emit("Stored terminal records could not be read.")
            return
        if not self.isInterruptionRequested():
            self.loaded.emit(snapshot)


class TerminalActionWorker(QThread):
    """Apply one paper control. It does not submit an order."""

    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, settings: Settings, action: str, payload: object) -> None:
        super().__init__()
        self._settings = settings
        self._action = action
        self._payload = payload

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            message = _run(self._settings, self._action, self._payload)
        except CyvoraError as exc:
            self.failed.emit(str(exc))
            return
        except Exception:
            self.failed.emit("The terminal action could not be completed.")
            return
        if not self.isInterruptionRequested():
            self.finished_ok.emit(message)


def _run(settings: Settings, action: str, payload: object) -> str:
    now = datetime.now(UTC)
    repository = PostgresTerminalRepository(settings)
    if action == "pause":
        repository.pause_entries(now)
        return "New paper entries are paused. No order was submitted."
    if action == "resume":
        repository.resume_entries(now)
        return "Paper entry evaluation was resumed. Live trading stays locked."
    if action == "activate":
        if not isinstance(payload, str):
            raise CyvoraError("A profile id is required.")
        repository.activate_profile(payload, now)
        return "The paper profile is selected. Shield limits are unchanged."
    if action == "profile":
        if not isinstance(payload, tuple) or len(payload) != 4:
            raise CyvoraError("A profile name and strategy list are required.")
        profile_id, name, strategies, threshold = payload
        if not isinstance(profile_id, str) or not isinstance(name, str):
            raise CyvoraError("A profile name and strategy list are required.")
        if not isinstance(strategies, tuple):
            raise CyvoraError("A profile name and strategy list are required.")
        if threshold is not None and not isinstance(threshold, str):
            raise CyvoraError("A recorded signal threshold is invalid.")
        repository.save_profile(
            profile_id,
            name,
            strategies,
            active=False,
            signal_threshold=threshold,
            now=now,
        )
        return "The paper profile was stored. It does not start a strategy."
    if action == "preferences":
        if not isinstance(payload, NotificationPreferences):
            raise CyvoraError("Notification settings are invalid.")
        repository.save_preferences(payload, now)
        return "Notification settings were stored. Telegram delivery stays off."
    if action in {"start", "stop"}:
        if not isinstance(payload, str):
            raise CyvoraError("A strategy id is required.")
        _strategy(settings, payload, start=action == "start")
        verb = "started" if action == "start" else "stopped"
        return f"The strategy was {verb}. No order was submitted."
    raise CyvoraError("That terminal action is not available.")


def _strategy(settings: Settings, strategy_id: str, *, start: bool) -> None:
    store = PostgresTradingRepository(settings)

    def clock() -> datetime:
        return datetime.now(UTC)

    gateway = PaperExecutionGateway(settings.execution_mode, store, clock)
    manager = StrategyManager(settings.execution_mode, store, gateway, clock)
    if start:
        manager.start(strategy_id)
        return
    manager.stop(strategy_id)
