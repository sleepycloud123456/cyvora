"""Stored performance. Research books are not combined with the operator book."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from apps.desktop.charts.series_chart import SeriesChart
from apps.desktop.components.disclosure import DetailDisclosure
from domain.terminal import AnalyticsView
from terminal.present import analytics_text


class AnalyticsPage(QWidget):
    """Equity, drawdown, and stored comparisons."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(16)
        self.notice = QLabel("Terminal storage has not been read.")
        self.notice.setObjectName("EmptyState")
        self.notice.setWordWrap(True)
        self.equity = SeriesChart("No equity curve.")
        self.drawdown = SeriesChart("No drawdown series.")
        self.summary = QLabel("")
        self.summary.setObjectName("Notice")
        self.summary.setWordWrap(True)
        self.method = QLabel(
            "Stored paper analytics. Sharpe and Sortino wait for 30 equity changes. "
            "Research rows are separate books and are not deployed."
        )
        self.method.setObjectName("Notice")
        self.method.setWordWrap(True)
        self.full_report = QLabel("")
        self.full_report.setObjectName("Notice")
        self.full_report.setWordWrap(True)
        self.details = DetailDisclosure("Details")
        self.details.add(self.method)
        self.details.add(self.full_report)
        layout.addWidget(self.notice)
        layout.addWidget(self.equity)
        layout.addWidget(self.drawdown)
        layout.addWidget(self.summary)
        layout.addWidget(self.details)
        layout.addStretch(1)

    def show_message(self, text: str) -> None:
        self.notice.setText(text)
        self.notice.setVisible(True)
        self.summary.setText("")
        self.full_report.setText("")
        self.details.setVisible(False)
        self.equity.set_points([])
        self.drawdown.set_points([])

    def show_analytics(self, view: AnalyticsView) -> None:
        text = analytics_text(view)
        lines = text.splitlines()
        self.notice.setVisible(False)
        self.equity.set_points([value for _day, value in view.equity_points])
        self.drawdown.set_points([value for _day, value in view.drawdown_points])
        self.summary.setText("\n".join(lines[:4]))
        self.full_report.setText(text)
        self.details.setVisible(True)
