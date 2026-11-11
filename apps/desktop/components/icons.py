"""Small geometric icons painted for the rail. No icon font is required."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

_Painter = Callable[[QPainter, QRectF], None]


def _pen(color: QColor) -> QPen:
    pen = QPen(color)
    pen.setWidthF(1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def paint_icon(painter: QPainter, kind: str, color: QColor, box: QRectF) -> None:
    """Draw a 24-unit icon centered in `box`."""

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(_pen(color))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    side = min(box.width(), box.height())
    scale = side / 24.0
    painter.translate(box.center().x(), box.center().y())
    painter.scale(scale, scale)
    painter.translate(-12.0, -12.0)
    draw = _ICONS.get(kind, _dashboard)
    draw(painter, QRectF(0, 0, 24, 24))
    painter.restore()


def _dashboard(painter: QPainter, _box: QRectF) -> None:
    gap = 2.4
    size = (24.0 - gap) / 2.0
    for row in (0.0, 1.0):
        for col in (0.0, 1.0):
            painter.drawRoundedRect(
                QRectF(col * (size + gap), row * (size + gap), size, size),
                2.2,
                2.2,
            )


def _positions(painter: QPainter, _box: QRectF) -> None:
    painter.drawRoundedRect(QRectF(3, 4, 18, 16), 2.5, 2.5)
    painter.drawLine(7, 9, 17, 9)
    painter.drawLine(7, 13, 13, 13)


def _history(painter: QPainter, _box: QRectF) -> None:
    painter.drawEllipse(QRectF(3, 3, 18, 18))
    painter.drawLine(12, 12, 12, 7)
    painter.drawLine(12, 12, 16, 14)


def _paper(painter: QPainter, _box: QRectF) -> None:
    painter.drawRoundedRect(QRectF(5, 2.5, 14, 19), 2, 2)
    painter.drawLine(8, 8, 16, 8)
    painter.drawLine(8, 12, 16, 12)
    painter.drawLine(8, 16, 13, 16)


def _strategies(painter: QPainter, _box: QRectF) -> None:
    painter.drawEllipse(QRectF(2, 9, 6, 6))
    painter.drawEllipse(QRectF(16, 2, 6, 6))
    painter.drawEllipse(QRectF(16, 16, 6, 6))
    painter.drawLine(8, 12, 16, 6)
    painter.drawLine(8, 12, 16, 18)


def _backtest(painter: QPainter, _box: QRectF) -> None:
    painter.drawLine(3, 20, 21, 20)
    painter.drawLine(4, 16, 8, 12)
    painter.drawLine(8, 12, 12, 14)
    painter.drawLine(12, 14, 20, 5)


def _shield(painter: QPainter, _box: QRectF) -> None:
    painter.drawLine(12, 3, 20, 6)
    painter.drawLine(20, 6, 20, 12)
    painter.drawLine(20, 12, 12, 21)
    painter.drawLine(12, 21, 4, 12)
    painter.drawLine(4, 12, 4, 6)
    painter.drawLine(4, 6, 12, 3)


def _analytics(painter: QPainter, _box: QRectF) -> None:
    painter.drawRoundedRect(QRectF(3, 12, 4, 8), 1, 1)
    painter.drawRoundedRect(QRectF(10, 7, 4, 13), 1, 1)
    painter.drawRoundedRect(QRectF(17, 3, 4, 17), 1, 1)


def _notifications(painter: QPainter, _box: QRectF) -> None:
    painter.drawLine(12, 3, 12, 4)
    painter.drawArc(QRectF(5, 4, 14, 12), 0, 180 * 16)
    painter.drawLine(5, 12, 19, 12)
    painter.drawLine(5, 12, 4, 15)
    painter.drawLine(19, 12, 20, 15)
    painter.drawLine(4, 15, 20, 15)
    painter.drawArc(QRectF(9, 15, 6, 5), 200 * 16, 140 * 16)


def _health(painter: QPainter, _box: QRectF) -> None:
    painter.drawLine(2, 12, 6, 12)
    painter.drawLine(6, 12, 9, 6)
    painter.drawLine(9, 6, 13, 18)
    painter.drawLine(13, 18, 16, 12)
    painter.drawLine(16, 12, 22, 12)


def _radar(painter: QPainter, _box: QRectF) -> None:
    painter.drawEllipse(QRectF(3, 3, 18, 18))
    painter.drawEllipse(QRectF(8, 8, 8, 8))
    painter.drawLine(16, 16, 21, 21)


def _portfolio(painter: QPainter, _box: QRectF) -> None:
    painter.drawRoundedRect(QRectF(3, 6, 18, 14), 2, 2)
    painter.drawLine(3, 10, 21, 10)
    painter.drawLine(8, 6, 8, 3)
    painter.drawLine(16, 6, 16, 3)


def _analyst(painter: QPainter, _box: QRectF) -> None:
    painter.drawEllipse(QRectF(4, 4, 16, 16))
    painter.drawEllipse(QRectF(10, 9, 4, 4))


def _settings(painter: QPainter, _box: QRectF) -> None:
    painter.drawEllipse(QRectF(8, 8, 8, 8))
    for index in range(8):
        painter.save()
        painter.translate(12, 12)
        painter.rotate(index * 45)
        painter.drawLine(0, -7, 0, -11)
        painter.restore()


_ICONS: dict[str, _Painter] = {
    "dashboard": _dashboard,
    "positions": _positions,
    "history": _history,
    "paper": _paper,
    "strategies": _strategies,
    "backtest": _backtest,
    "shield": _shield,
    "analytics": _analytics,
    "notifications": _notifications,
    "health": _health,
    "radar": _radar,
    "portfolio": _portfolio,
    "analyst": _analyst,
    "settings": _settings,
}
