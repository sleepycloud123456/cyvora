"""Icons-only sidebar. The page name is the tooltip."""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QEnterEvent, QFocusEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QButtonGroup, QFrame, QToolButton, QVBoxLayout, QWidget

from apps.desktop.components.icons import paint_icon
from apps.desktop.motion import animations_enabled
from apps.desktop.navigation import NavItem
from apps.desktop.themes.palette import ACCENT_RGB, GLOW_RGB, MUTED, SOFT_RGB


class NavButton(QToolButton):
    """One rail destination. Glow eases in on hover, focus, and the active page."""

    def __init__(self, name: str, icon: str) -> None:
        super().__init__()
        self._icon = icon
        self._glow = 0.0
        self._animation: QPropertyAnimation | None = None
        self.setObjectName("NavButton")
        self.setFixedSize(QSize(52, 48))
        self.setCheckable(True)
        self.setToolTip(name)
        self.setAccessibleName(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAutoRaise(True)

    def get_glow(self) -> float:
        return self._glow

    def set_glow(self, value: float) -> None:
        self._glow = float(value)
        self.update()

    glow = Property(float, get_glow, set_glow)

    def set_glow_target(self, target: float, *, animate: bool) -> None:
        if self._animation is not None:
            self._animation.stop()
            self._animation = None
        if not animate or not animations_enabled():
            self.set_glow(target)
            return
        animation = QPropertyAnimation(self, b"glow", self)
        animation.setDuration(160)
        animation.setStartValue(self._glow)
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.start()
        self._animation = animation

    def enterEvent(self, event: QEnterEvent) -> None:
        self.set_glow_target(1.0, animate=True)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self.set_glow_target(1.0 if self.isChecked() else 0.0, animate=True)
        super().leaveEvent(event)

    def focusInEvent(self, event: QFocusEvent) -> None:
        self.set_glow_target(1.0, animate=True)
        super().focusInEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        if not self.underMouse():
            self.set_glow_target(1.0 if self.isChecked() else 0.0, animate=True)
        super().focusOutEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isDown() and animations_enabled():
            painter.translate(self.width() / 2, self.height() / 2)
            painter.scale(0.94, 0.94)
            painter.translate(-self.width() / 2, -self.height() / 2)
        glow = 1.0 if self.isChecked() else self._glow
        rect = QRectF(6, 4, self.width() - 12, self.height() - 8)
        if glow > 0.01:
            wash = QColor(*GLOW_RGB, int(28 + 70 * glow))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(wash)
            painter.drawRoundedRect(rect, 12, 12)
            edge = QPen(QColor(*ACCENT_RGB, int(210 * glow)))
            edge.setWidthF(1.25)
            painter.setPen(edge)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        if self.hasFocus():
            focus = QPen(QColor(*SOFT_RGB, 180))
            focus.setWidthF(1.1)
            painter.setPen(focus)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 14, 14)
        color = QColor("#E9D5FF" if glow > 0.35 or self.isChecked() else MUTED)
        icon_box = QRectF(self.width() / 2 - 11, self.height() / 2 - 11, 22, 22)
        paint_icon(painter, self._icon, color, icon_box)
        painter.end()


class BrandMark(QWidget):
    """Small monogram. The slogan lives on the tooltip and in the page header."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("BrandMark")
        self.setFixedSize(QSize(52, 52))
        self.setToolTip("CYVORA. TRADE BEYOND LIMITS.")

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(*ACCENT_RGB, 230))
        pen.setWidthF(1.6)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRectF(14, 10, 24, 24)
        painter.drawArc(rect, 40 * 16, 280 * 16)
        painter.drawEllipse(QRectF(23, 19, 6, 6))
        painter.end()


class NavRail(QFrame):
    """Slim icon column. Names are tooltips, not labels."""

    page_selected = Signal(str)

    def __init__(self, items: tuple[NavItem, ...]) -> None:
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(76)
        self._buttons: dict[str, NavButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 22, 12, 22)
        layout.setSpacing(8)
        layout.addWidget(BrandMark(), alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(18)
        for item in items:
            button = NavButton(item.name, item.icon)
            button.clicked.connect(lambda _checked=False, name=item.name: self._choose(name))
            self._group.addButton(button)
            self._buttons[item.name] = button
            layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

    def names(self) -> tuple[str, ...]:
        return tuple(self._buttons)

    def button(self, name: str) -> NavButton:
        return self._buttons[name]

    def mark(self, name: str) -> None:
        """Reflect the open page. A hidden page clears the active icon."""

        selected = self._buttons.get(name)
        self._group.setExclusive(False)
        for key, button in self._buttons.items():
            button.setChecked(key == name)
            button.set_glow_target(1.0 if key == name else 0.0, animate=False)
        self._group.setExclusive(True)
        if selected is None:
            return

    def _choose(self, name: str) -> None:
        self.page_selected.emit(name)
