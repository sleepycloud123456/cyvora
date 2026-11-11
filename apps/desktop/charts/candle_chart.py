"""Stored candle chart. It draws only candles the radar cycle saved."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class CandleChart(QWidget):
    """A small OHLC chart. An empty series stays empty."""

    def __init__(self) -> None:
        super().__init__()
        self._candles: list[tuple[Decimal, Decimal, Decimal, Decimal]] = []
        self.setFixedHeight(188)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setObjectName("CandleChart")

    def set_rows(self, rows: list[tuple[str | None, str | None, str | None, str | None]]) -> None:
        parsed: list[tuple[Decimal, Decimal, Decimal, Decimal]] = []
        for open_, high, low, close in rows:
            values = [_decimal(open_), _decimal(high), _decimal(low), _decimal(close)]
            if any(item is None for item in values):
                continue
            opened, high_value, low_value, closed = values
            if opened is None or high_value is None or low_value is None or closed is None:
                continue
            parsed.append((opened, high_value, low_value, closed))
        self._candles = parsed
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        frame = QPen(QColor(168, 85, 247, 96))
        frame.setWidthF(1.0)
        painter.setPen(frame)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 12, 12)
        if len(self._candles) < 2:
            painter.setPen(QColor("#B7AEC4"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No stored candle series for this token.",
            )
            painter.end()
            return
        highs = [item[1] for item in self._candles]
        lows = [item[2] for item in self._candles]
        top = max(highs)
        bottom = min(lows)
        span = top - bottom
        if span <= 0:
            span = Decimal(1)
        width = max(self.width(), 1)
        height = max(self.height() - 16, 1)
        slot = width / len(self._candles)
        for index, (opened, high, low, closed) in enumerate(self._candles):
            color = QColor("#C084FC") if closed >= opened else QColor("#F87171")
            painter.setPen(color)
            x = slot * index + slot / 2
            y_high = _y(high, bottom, span, height)
            y_low = _y(low, bottom, span, height)
            painter.drawLine(QPointF(x, y_high), QPointF(x, y_low))
            body_top = _y(max(opened, closed), bottom, span, height)
            body_bottom = _y(min(opened, closed), bottom, span, height)
            body_height = max(body_bottom - body_top, 1.0)
            painter.fillRect(
                int(x - slot * 0.25),
                int(body_top),
                max(int(slot * 0.5), 1),
                int(body_height),
                color,
            )
        painter.end()


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _y(value: Decimal, bottom: Decimal, span: Decimal, height: int) -> float:
    fraction = (value - bottom) / span
    return float(8 + (Decimal(1) - fraction) * Decimal(height))
