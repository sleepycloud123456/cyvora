"""Stored performance. Research books are not combined with the operator book."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from apps.desktop.charts.series_chart import SeriesChart
from domain.terminal import AnalyticsView
from terminal.present import analytics_text


class AnalyticsPage(QWidget):
    """Equity, drawdown, and stored comparisons."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        self.notice = QLabel("Terminal storage has not been read.")
        self.notice.setObjectName("Notice")
        self.notice.setWordWrap(True)
        self.equity = SeriesChart("No stored equity curve. At least two baselines are required.")
        self.drawdown = SeriesChart("No stored drawdown series.")
        self.summary = QLabel("")
        self.summary.setObjectName("Notice")
        self.summary.setWordWrap(True)
        layout.addWidget(self.notice)
        layout.addWidget(self.equity)
        layout.addWidget(self.drawdown)
        layout.addWidget(self.summary, stretch=1)

    def show_message(self, text: str) -> None:
        self.notice.setText(text)
        self.summary.setText("")
        self.equity.set_points([])
        self.drawdown.set_points([])

    def show_analytics(self, view: AnalyticsView) -> None:
        self.notice.setText(
            "Stored paper analytics. Sharpe and Sortino wait for 30 equity changes. "
            "Research rows are separate books and are not deployed."
        )
        self.equity.set_points([value for _day, value in view.equity_points])
        self.drawdown.set_points([value for _day, value in view.drawdown_points])
        self.summary.setText(analytics_text(view))
