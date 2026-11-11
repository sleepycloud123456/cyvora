"""Dashboard with foundation status and stored paper figures."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from apps.desktop.components.disclosure import DetailDisclosure
from apps.desktop.components.hologram import Hologram
from apps.desktop.components.status_card import StatusCard
from domain.status import StatusSnapshot
from domain.terminal import PortfolioView
from terminal.present import money

_PRIMARY = (
    "verified_equity",
    "open_positions",
    "unrealized",
    "daily_pnl",
    "total_pnl",
    "risk_status",
)


class DashboardPage(QWidget):
    """Status and the stored paper book. Missing wallet figures stay unavailable."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(0)
        self.notice = QLabel(
            "Paper figures come from the stored book. Wallet SOL and USD value "
            "are not available. A Shield figure is not a live balance."
        )
        self.notice.setObjectName("Notice")
        self.notice.setWordWrap(True)
        self.application_card = StatusCard("Application")
        self.database_card = StatusCard("Database")
        self.backend_card = StatusCard("Backend")
        self.gmgn_card = StatusCard("GMGN")
        self._metrics = {name: StatusCard(title) for name, title in _METRIC_TITLES}
        self.hologram = Hologram()
        self.recent = QLabel("Recent paper orders have not been loaded.")
        self.recent.setObjectName("EmptyState")
        self.recent.setWordWrap(True)
        self.details = DetailDisclosure("Details")
        self.details.add(self.notice)

        hero = QHBoxLayout()
        hero.setSpacing(36)
        figures = QGridLayout()
        figures.setHorizontalSpacing(16)
        figures.setVerticalSpacing(16)
        for index, name in enumerate(_PRIMARY):
            figures.addWidget(self._metrics[name], index // 2, index % 2)
        hero.addLayout(figures, stretch=1)
        hero.addWidget(self.hologram, stretch=0)

        status = QHBoxLayout()
        status.setSpacing(16)
        status.addWidget(self.database_card)
        status.addWidget(self.backend_card)
        status.addWidget(self.gmgn_card)
        status.addWidget(self.application_card)

        secondary = QGridLayout()
        secondary.setHorizontalSpacing(16)
        secondary.setVerticalSpacing(16)
        hidden = [name for name, _title in _METRIC_TITLES if name not in _PRIMARY]
        for index, name in enumerate(hidden):
            secondary.addWidget(self._metrics[name], index // 3, index % 3)
        secondary_host = QWidget()
        secondary_host.setLayout(secondary)
        self.details.add(secondary_host)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 12, 0, 0)
        body_layout.setSpacing(28)
        body_layout.addLayout(hero)
        body_layout.addLayout(status)
        body_layout.addWidget(self.recent)
        body_layout.addWidget(self.details)
        body_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        self._show_metric_message("Not checked", "The paper book has not been read.")

    def set_checking(self) -> None:
        for card in self._cards():
            card.set_status("Checking...", "A background status check is running.")

    def set_idle(self) -> None:
        for card in self._cards():
            card.set_status("Not checked", "The status probe is idle in this session.")
        self._show_metric_message("Not checked", "The paper book has not been read.")

    def show_probe_failure(self, message: str) -> None:
        self.database_card.set_status("unknown", message)
        self.backend_card.set_status("unknown", message)
        self.gmgn_card.set_status("unknown", message)

    def apply_snapshot(self, snapshot: StatusSnapshot) -> None:
        self.application_card.apply(snapshot.application)
        self.database_card.apply(snapshot.database)
        self.backend_card.apply(snapshot.backend)
        self.gmgn_card.apply(snapshot.gmgn)

    def show_portfolio_message(self, text: str) -> None:
        self._show_metric_message("unavailable", text)
        self.recent.setText(text)

    def show_portfolio(self, view: PortfolioView) -> None:
        self._set_money("verified_equity", view.verified_equity, None, view.verified_equity_detail)
        self._metrics["sol_balance"].set_status("unavailable", view.sol_balance_detail)
        self._metrics["usd_value"].set_status("unavailable", view.usd_detail)
        self._set_money("allocated", view.allocated, view.allocated_unit, view.allocated_detail)
        self._set_money("available", view.available, None, view.available_detail)
        self._metrics["open_positions"].set_status(
            str(view.open_positions), "Open paper positions."
        )
        self._set_money("unrealized", view.unrealized, None, view.unrealized_detail)
        self._set_money("realized", view.realized, view.realized_unit, view.realized_detail)
        self._set_money("daily_pnl", view.daily_pnl, None, view.daily_pnl_detail)
        self._set_money("total_pnl", view.total_pnl, None, view.total_pnl_detail)
        self._set_money("win_rate", view.win_rate, None, view.win_rate_detail)
        self._set_money("average_profit", view.average_profit, None, view.average_profit_detail)
        self._metrics["active_strategies"].set_status(
            str(view.active_strategies), "Strategies in the RUNNING state."
        )
        self._metrics["market_condition"].set_status(view.market_condition, view.market_detail)
        self._metrics["risk_status"].set_status(view.risk_status, view.risk_detail)
        self._set_money("exposure", view.exposure, None, view.exposure_detail)
        self._set_money("drawdown", view.max_drawdown, None, view.drawdown_detail)
        self._set_money(
            "sol_reserve", view.sol_reserve_fraction, "fraction", view.sol_reserve_detail
        )
        if not view.recent:
            self.recent.setText("No simulated orders are stored.")
            return
        lines = [
            f"{item.symbol} {item.side} {item.state} {item.shield_decision}" for item in view.recent
        ]
        self.recent.setText("Recent paper orders: " + "; ".join(lines))

    def _cards(self) -> tuple[StatusCard, ...]:
        return (self.application_card, self.database_card, self.backend_card, self.gmgn_card)

    def _show_metric_message(self, state: str, detail: str) -> None:
        for card in self._metrics.values():
            card.set_status(state, detail)

    def _set_money(self, name: str, value: Decimal | None, unit: str | None, detail: str) -> None:
        if value is None:
            self._metrics[name].set_status("unavailable", detail)
            return
        text = money(value)
        if unit:
            text = f"{text} {unit}"
        self._metrics[name].set_status(text, detail)


_METRIC_TITLES = (
    ("verified_equity", "Verified equity"),
    ("sol_balance", "SOL balance"),
    ("usd_value", "USD value"),
    ("allocated", "Allocated cost"),
    ("available", "Available"),
    ("open_positions", "Open positions"),
    ("unrealized", "Unrealized PnL"),
    ("realized", "Realized PnL"),
    ("daily_pnl", "Daily PnL"),
    ("total_pnl", "Total PnL"),
    ("win_rate", "Win rate"),
    ("average_profit", "Average result"),
    ("active_strategies", "Active strategies"),
    ("market_condition", "Market condition"),
    ("risk_status", "Risk status"),
    ("exposure", "Exposure"),
    ("drawdown", "Max drawdown"),
    ("sol_reserve", "SOL reserve rule"),
)
