"""Dashboard hologram. A painted wireframe, not a second rendering engine.

Qt Quick 3D and a live GL context are uneven on offscreen and software GL.
This widget projects a sphere in software, keeps a single coarse timer, and
stops that timer when the page is hidden or motion is off.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QHideEvent,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QPen,
    QShowEvent,
)
from PySide6.QtWidgets import QWidget

from apps.desktop.motion import animations_enabled
from apps.desktop.themes.palette import ACCENT_RGB, GLOW_RGB, SOFT_RGB

_Point = tuple[float, float, float]
_Line = tuple[_Point, ...]


def _mesh() -> tuple[_Line, ...]:
    lines: list[_Line] = []
    latitudes = 5
    longitudes = 8
    segments = 40
    for index in range(1, latitudes):
        phi = math.pi * index / latitudes
        ring: list[_Point] = []
        for step in range(segments + 1):
            theta = 2 * math.pi * step / segments
            ring.append(
                (
                    math.sin(phi) * math.cos(theta),
                    math.cos(phi),
                    math.sin(phi) * math.sin(theta),
                )
            )
        lines.append(tuple(ring))
    for index in range(longitudes):
        theta = 2 * math.pi * index / longitudes
        meridian: list[_Point] = []
        for step in range(segments + 1):
            phi = math.pi * step / segments
            meridian.append(
                (
                    math.sin(phi) * math.cos(theta),
                    math.cos(phi),
                    math.sin(phi) * math.sin(theta),
                )
            )
        lines.append(tuple(meridian))
    outer: list[_Point] = []
    inner: list[_Point] = []
    for step in range(segments + 1):
        theta = 2 * math.pi * step / segments
        outer.append((1.32 * math.cos(theta), 0.0, 1.32 * math.sin(theta)))
        inner.append((0.38 * math.cos(theta), 0.0, 0.38 * math.sin(theta)))
    lines.append(tuple(outer))
    lines.append(tuple(inner))
    return tuple(lines)


_LINES = _mesh()


class Hologram(QWidget):
    """Rotating purple wireframe with scanlines, a cone, and a soft flicker."""

    def __init__(self, *, animated: bool | None = None) -> None:
        super().__init__()
        self.setObjectName("Hologram")
        self.setFixedSize(300, 360)
        self._override = animated
        self._phase = 0.7
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._timer.timeout.connect(self._tick)

    def animating(self) -> bool:
        return self._timer.isActive()

    def stop(self) -> None:
        self._timer.stop()

    def sync(self) -> None:
        """Start or stop the timer from the current motion flag."""

        self._sync_timer()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event: QHideEvent) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _motion(self) -> bool:
        if self._override is not None:
            return self._override
        return animations_enabled()

    def _sync_timer(self) -> None:
        if self._motion() and self.isVisible():
            if not self._timer.isActive():
                self._timer.start()
            return
        self._timer.stop()

    def _tick(self) -> None:
        if not self.isVisible():
            self._timer.stop()
            return
        self._phase = (self._phase + 0.007) % (math.tau)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#000000"))
        _paint_cone(painter, self.width(), self.height())
        _paint_mesh(painter, self.width(), self.height(), self._phase)
        _paint_scanlines(painter, self.width(), self.height(), self._phase)
        painter.end()


def _rotate(point: _Point, phase: float) -> _Point:
    x, y, z = point
    cosine = math.cos(phase)
    sine = math.sin(phase)
    rotated_x = x * cosine + z * sine
    rotated_z = -x * sine + z * cosine
    tilt = 0.62
    tilt_cos = math.cos(tilt)
    tilt_sin = math.sin(tilt)
    tilted_y = y * tilt_cos - rotated_z * tilt_sin
    tilted_z = y * tilt_sin + rotated_z * tilt_cos
    return rotated_x, tilted_y, tilted_z


def _project(
    point: _Point, origin_x: float, origin_y: float, scale: float
) -> tuple[float, float, float]:
    depth = point[2] + 3.5
    factor = scale / depth
    return origin_x + point[0] * factor, origin_y - point[1] * factor, depth


def _paint_cone(painter: QPainter, width: int, height: int) -> None:
    center_x = width / 2
    base_y = height * 0.84
    radius = width * 0.34
    top_y = height * 0.30
    gradient = QLinearGradient(center_x, top_y, center_x, base_y)
    gradient.setColorAt(0.0, QColor(*GLOW_RGB, 0))
    gradient.setColorAt(0.55, QColor(*GLOW_RGB, 18))
    gradient.setColorAt(1.0, QColor(*ACCENT_RGB, 48))
    path_left = center_x - radius
    path_right = center_x + radius
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawPolygon(
        [
            QPointF(center_x - 28, top_y),
            QPointF(center_x + 28, top_y),
            QPointF(path_right, base_y),
            QPointF(path_left, base_y),
        ]
    )
    pen = QPen(QColor(*ACCENT_RGB, 90))
    pen.setWidthF(1.1)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(center_x, base_y), radius, 11)
    painter.drawEllipse(QPointF(center_x, base_y), radius * 0.55, 6)
    painter.drawLine(QPointF(path_left, base_y), QPointF(center_x - 28, top_y))
    painter.drawLine(QPointF(path_right, base_y), QPointF(center_x + 28, top_y))


def _paint_mesh(painter: QPainter, width: int, height: int, phase: float) -> None:
    origin_x = width / 2
    origin_y = height * 0.40
    scale = min(width, height) * 0.92
    flicker = 0.9 + 0.1 * math.sin(phase * 23.0)
    segments: list[tuple[float, QPointF, QPointF]] = []
    for line in _LINES:
        projected = [_project(_rotate(point, phase), origin_x, origin_y, scale) for point in line]
        for start, end in zip(projected, projected[1:], strict=False):
            depth = (start[2] + end[2]) / 2
            segments.append((depth, QPointF(start[0], start[1]), QPointF(end[0], end[1])))
    segments.sort(key=lambda item: item[0])
    painter.save()
    painter.setOpacity(flicker)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    for depth, left, right in segments:
        near = max(0.0, min(1.0, (depth - 2.2) / 2.4))
        alpha = int(18 + 70 * near)
        glow = QPen(QColor(*GLOW_RGB, alpha))
        glow.setWidthF(3.4)
        painter.setPen(glow)
        painter.drawLine(left, right)
        magenta = QPen(QColor(255, 90, 220, max(alpha // 3, 8)))
        magenta.setWidthF(1.2)
        painter.setPen(magenta)
        painter.drawLine(left + QPointF(1.4, 0), right + QPointF(1.4, 0))
        cyan = QPen(QColor(120, 190, 255, max(alpha // 4, 6)))
        cyan.setWidthF(1.1)
        painter.setPen(cyan)
        painter.drawLine(left - QPointF(1.4, 0), right - QPointF(1.4, 0))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    for depth, left, right in segments:
        near = max(0.0, min(1.0, (depth - 2.2) / 2.4))
        core = QPen(QColor(*SOFT_RGB, int(70 + 170 * near)))
        core.setWidthF(1.15)
        painter.setPen(core)
        painter.drawLine(left, right)
    painter.restore()


def _paint_scanlines(painter: QPainter, width: int, height: int, phase: float) -> None:
    line = QColor(*ACCENT_RGB, 16)
    painter.setPen(line)
    for y in range(0, height, 4):
        painter.drawLine(0, y, width, y)
    band = int((phase * 48) % height)
    gradient = QLinearGradient(0, band - 10, 0, band + 14)
    gradient.setColorAt(0.0, QColor(*SOFT_RGB, 0))
    gradient.setColorAt(0.5, QColor(*ACCENT_RGB, 36))
    gradient.setColorAt(1.0, QColor(*SOFT_RGB, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRect(QRectF(0, band - 10, width, 24))
