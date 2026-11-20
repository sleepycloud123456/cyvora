"""The dashboard view of the autonomous paper trader."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from domain.paper_trader import (
    PaperTraderView,
    StoredTraderCycle,
    StoredTraderDecision,
    unavailable_trader,
)

_KILL = {
    "released": "The kill switch is released. Shield still evaluates paper orders.",
    "engaged": "The kill switch is engaged. New paper orders are refused.",
    "unreadable": "The kill switch could not be read. New paper orders stay blocked.",
    "not_configured": "The kill switch is not stored.",
    "not_checked": "The kill switch was not read for this pass.",
    "unknown": "The kill switch was not read with this view.",
}


def build_paper_trader_view(
    cycle: StoredTraderCycle | None,
    decisions: tuple[StoredTraderDecision, ...],
    equity: tuple[Decimal | None, ...],
    *,
    now: datetime,
    stale_after_seconds: int,
    bankroll: Decimal | None,
) -> PaperTraderView:
    """Describe the latest stored pass. A missing cycle is not a running trader."""

    if cycle is None:
        return PaperTraderView(
            status="not running",
            status_detail=(
                "The paper trader has not completed a cycle. Live trading stays locked."
            ),
            kill_switch="unknown",
            kill_detail=_KILL["unknown"],
            halt_entries=False,
            entries_blocked=False,
            bankroll=bankroll,
            equity_points=tuple(point for point in equity if point is not None),
            decisions=tuple(_line(item) for item in decisions),
            observed_at=None,
            live_trading_enabled=False,
        )
    status = cycle.status
    detail = cycle.detail
    observed = cycle.finished_at
    if observed.tzinfo is not None and now.tzinfo is not None:
        age = (now - observed).total_seconds()
        if age > stale_after_seconds:
            status = "stale"
            detail = (
                f"The last paper trader cycle finished at {observed.isoformat()}. "
                "It is outside the freshness window. "
                f"{cycle.detail}"
            )
    return PaperTraderView(
        status=status,
        status_detail=detail,
        kill_switch=cycle.kill_switch,
        kill_detail=_KILL.get(cycle.kill_switch, _KILL["unknown"]),
        halt_entries=cycle.halt_entries,
        entries_blocked=cycle.entries_blocked,
        bankroll=bankroll,
        equity_points=tuple(point for point in equity if point is not None),
        decisions=tuple(_line(item) for item in decisions),
        observed_at=observed,
        live_trading_enabled=False,
    )


def empty_because(detail: str) -> PaperTraderView:
    """Use this when the book could not be read."""

    return unavailable_trader(detail)


def _line(row: StoredTraderDecision) -> str:
    score = "score unknown" if row.score is None else f"score {row.score}"
    return f"{row.symbol} {row.action} {row.reason} ({score})"
