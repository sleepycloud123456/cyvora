"""Page motion for the terminal. A startup flag turns the timers off."""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QParallelAnimationGroup,
    QPropertyAnimation,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget, QVBoxLayout, QWidget

_ENABLED = True


def configure_motion(enabled: bool) -> None:
    """Record whether this process should animate the desktop."""

    global _ENABLED
    _ENABLED = enabled


def animations_enabled() -> bool:
    """Return the process flag set at window startup."""

    return _ENABLED


class PageStage(QWidget):
    """Holds the page stack and a short settle offset used during a fade."""

    def __init__(self) -> None:
        super().__init__()
        self.stack = QStackedWidget()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addWidget(self.stack)
        self._settle = 0.0
        self._token = 0
        self._animation: QParallelAnimationGroup | None = None

    def get_settle(self) -> float:
        return self._settle

    def set_settle(self, value: float) -> None:
        self._settle = float(value)
        margin = max(int(self._settle), 0)
        self._layout.setContentsMargins(margin // 5, margin, margin // 5, 0)

    settle = Property(float, get_settle, set_settle)

    def show_widget(self, widget: QWidget) -> None:
        """Switch pages immediately, then fade and settle when motion is on."""

        self._token += 1
        token = self._token
        if self._animation is not None:
            self._animation.stop()
            self._animation = None
        _clear_effect(self.stack)
        self.set_settle(0.0)
        self.stack.setCurrentWidget(widget)
        if not animations_enabled():
            return
        effect = QGraphicsOpacityEffect(self.stack)
        effect.setOpacity(0.4)
        self.stack.setGraphicsEffect(effect)
        self.set_settle(16.0)
        fade = QPropertyAnimation(effect, b"opacity", self)
        fade.setDuration(240)
        fade.setStartValue(0.4)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        settle = QPropertyAnimation(self, b"settle", self)
        settle.setDuration(240)
        settle.setStartValue(16.0)
        settle.setEndValue(0.0)
        settle.setEasingCurve(QEasingCurve.Type.OutCubic)
        group = QParallelAnimationGroup(self)
        group.addAnimation(fade)
        group.addAnimation(settle)
        group.finished.connect(lambda: self._finish(token, effect))
        self._animation = group
        group.start()

    def _finish(self, token: int, effect: QGraphicsOpacityEffect) -> None:
        if token != self._token:
            return
        if self.stack.graphicsEffect() is effect:
            _clear_effect(self.stack)
        self.set_settle(0.0)
        self._animation = None


def _clear_effect(widget: QWidget) -> None:
    widget.setGraphicsEffect(None)  # type: ignore[arg-type]


def reveal(stage: PageStage, widget: QWidget) -> None:
    """Show `widget` on the stage."""

    stage.show_widget(widget)
