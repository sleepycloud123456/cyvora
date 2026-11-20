"""Reusable status card. The number stays visible. The explanation is a tooltip."""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QEvent, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QEnterEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from apps.desktop.motion import animations_enabled
from apps.desktop.themes.palette import ACCENT_RGB
from domain.status import ComponentStatus


class StatusCard(QFrame):
    """A labeled state. Hover draws a purple edge. The long detail is a tooltip."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("StatusCard")
        self.setMinimumHeight(92)
        self._glow = 0.0
        self._animation: QPropertyAnimation | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        self.state_label = QLabel("Not checked")
        self.state_label.setObjectName("StateValue")
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("CardDetail")
        self.detail_label.setWordWrap(True)
        self.detail_label.setVisible(False)
        layout.addWidget(title_label)
        layout.addWidget(self.state_label)
        layout.addWidget(self.detail_label)

    def get_glow(self) -> float:
        return self._glow

    def set_glow(self, value: float) -> None:
        self._glow = float(value)
        self.update()

    glow = Property(float, get_glow, set_glow)

    def set_status(self, state: str, detail: str) -> None:
        self.state_label.setText(state)
        self.detail_label.setText(detail)
        self.setToolTip(detail)

    def apply(self, status: ComponentStatus) -> None:
        self.set_status(status.state, status.detail)

    def enterEvent(self, event: QEnterEvent) -> None:
        self._animate_glow(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._animate_glow(0.0)
        super().leaveEvent(event)

    def _animate_glow(self, target: float) -> None:
        if self._animation is not None:
            self._animation.stop()
            self._animation = None
        if not animations_enabled():
            self.set_glow(target)
            return
        animation = QPropertyAnimation(self, b"glow", self)
        animation.setDuration(160)
        animation.setStartValue(self._glow)
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.start()
        self._animation = animation

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self._glow <= 0.02:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(*ACCENT_RGB, int(40 + 180 * self._glow)))
        pen.setWidthF(1.4)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 16, 16)
        painter.end()
