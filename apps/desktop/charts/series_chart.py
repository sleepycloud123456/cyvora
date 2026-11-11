"""A line chart for stored equity or drawdown points."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class SeriesChart(QWidget):
    """Plot stored points. Fewer than two points stays an empty state."""

    def __init__(self, empty: str) -> None:
        super().__init__()
        self._empty = empty
        self._points: list[Decimal] = []
        self.setFixedHeight(188)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setObjectName("SeriesChart")

    def set_points(self, points: list[Decimal]) -> None:
        self._points = points
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        frame = QPen(QColor(168, 85, 247, 96))
        frame.setWidthF(1.0)
        painter.setPen(frame)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 12, 12)
        if len(self._points) < 2:
            painter.setPen(QColor("#B7AEC4"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._empty)
            painter.end()
            return
        top = max(self._points)
        bottom = min(self._points)
        span = top - bottom
        if span <= 0:
            span = Decimal(1)
        width = max(self.width() - 16, 1)
        height = max(self.height() - 16, 1)
        step = width / (len(self._points) - 1)
        painter.setPen(QColor("#C084FC"))
        previous_x = 8.0
        previous_y = _y(self._points[0], bottom, span, height)
        for index, value in enumerate(self._points[1:], start=1):
            x = 8.0 + step * index
            y = _y(value, bottom, span, height)
            painter.drawLine(int(previous_x), int(previous_y), int(x), int(y))
            previous_x, previous_y = x, y
        painter.end()


def _y(value: Decimal, bottom: Decimal, span: Decimal, height: int) -> float:
    return float(height) - float((value - bottom) / span) * float(height) + 8
