"""Stored CYVORA Shield state. The page does not invent a portfolio."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from apps.desktop.components.disclosure import DetailDisclosure
from domain.shield import ShieldNotice, ShieldSnapshot
from intelligence.numbers import format_decimal


class ShieldPage(QWidget):
    """Show the persisted paper risk book or an explicit empty state."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(16)
        self.notice = QLabel()
        self.notice.setObjectName("EmptyState")
        self.notice.setWordWrap(True)
        self.headline = QLabel("")
        self.headline.setObjectName("Headline")
        self.headline.setWordWrap(True)
        self.body = QLabel()
        self.body.setObjectName("Notice")
        self.body.setWordWrap(True)
        self.aside = QLabel(
            "Stored paper risk records. These are not wallet balances, "
            "and a paper approval cannot submit a live order. "
            "A planned stop is not a guaranteed exit."
        )
        self.aside.setObjectName("Notice")
        self.aside.setWordWrap(True)
        self.details = DetailDisclosure("Details")
        self.details.add(self.aside)
        self.details.add(self.body)
        layout.addWidget(self.notice)
        layout.addWidget(self.headline)
        layout.addWidget(self.details)
        layout.addStretch(1)
        self.show_message("Shield storage has not been read.")

    def show_message(self, text: str) -> None:
        self.notice.setText(text)
        self.notice.setVisible(True)
        self.headline.setText("")
        self.headline.setVisible(False)
        self.body.setText("")
        self.details.setVisible(False)

    def show_snapshot(self, snapshot: ShieldSnapshot, notices: tuple[ShieldNotice, ...]) -> None:
        text = _lines(snapshot, notices)
        lines = text.splitlines()
        self.notice.setVisible(False)
        self.headline.setText("\n".join(lines[:4]))
        self.headline.setVisible(True)
        self.body.setText(text)
        self.details.setVisible(True)


def _lines(snapshot: ShieldSnapshot, notices: tuple[ShieldNotice, ...]) -> str:
    if snapshot.high_water_equity is None:
        equity = "No verified equity has been recorded."
    else:
        equity = f"High-water equity {_money(snapshot.high_water_equity)} SOL."
    posture = "breached" if snapshot.breach_latched or snapshot.halt_entries else "enforcing"
    reasons = ", ".join(snapshot.breach_reasons) if snapshot.breach_reasons else "none"
    daily = "No UTC-day baseline is stored."
    if snapshot.daily:
        current = max(snapshot.daily, key=lambda row: row.session_date)
        daily = (
            f"UTC {current.session_date.isoformat()} opened at "
            f"{_money(current.equity_at_open)} and was last verified at "
            f"{_money(current.last_equity)}."
        )
    note_lines = "\n".join(f"Notice: {notice.detail}" for notice in notices) or "No Shield notices."
    limits = snapshot.limits
    return "\n".join(
        (
            f"Posture: {posture}. Live trading is locked.",
            equity,
            f"Consecutive losing campaigns: {snapshot.consecutive_losses}.",
            f"Breach reasons: {reasons}.",
            daily,
            "Documented limits in force: "
            f"deployed {limits.max_deployed_fraction}, "
            f"SOL reserve {limits.min_sol_reserve_fraction}, "
            f"risk per trade {limits.risk_per_trade_fraction}, "
            f"daily loss {limits.daily_loss_fraction}, "
            f"drawdown {limits.max_drawdown_fraction}, "
            f"consecutive losses {limits.max_consecutive_losses}.",
            "A planned stop is not a guaranteed exit.",
            note_lines,
        )
    )


def _money(value: object) -> str:
    from decimal import Decimal

    if not isinstance(value, Decimal):
        return "none"
    text = format_decimal(value)
    return text if text is not None else "none"
