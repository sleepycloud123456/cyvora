"""A collapsed details block. Secondary copy stays out of the default view."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton, QVBoxLayout, QWidget


class DetailDisclosure(QWidget):
    """One-line toggle. The body is hidden until the operator opens it."""

    def __init__(self, label: str = "Details") -> None:
        super().__init__()
        self._label = label
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.toggle = QToolButton()
        self.toggle.setObjectName("DetailToggle")
        self.toggle.setText(label)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(False)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.toggle.toggled.connect(self._toggled)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(12)
        self.body.setVisible(False)
        layout.addWidget(self.toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.body)

    def add(self, widget: QWidget) -> None:
        self.body_layout.addWidget(widget)

    def _toggled(self, open_: bool) -> None:
        self.body.setVisible(open_)
        self.toggle.setText("Hide details" if open_ else self._label)
