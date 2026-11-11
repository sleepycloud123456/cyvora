"""Changes between stored Shield equity baselines. Missing days stay missing."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.shield import DailyBaseline


def ordered_baselines(daily: tuple[DailyBaseline, ...]) -> tuple[DailyBaseline, ...]:
    return tuple(sorted(daily, key=lambda row: row.session_date))


def equity_points(daily: tuple[DailyBaseline, ...]) -> tuple[tuple[date, Decimal], ...]:
    return tuple((row.session_date, row.last_equity) for row in ordered_baselines(daily))


def latest_daily_change(daily: tuple[DailyBaseline, ...]) -> tuple[Decimal | None, str]:
    """Return the newest stored equity change, or say why it is missing."""

    ordered = ordered_baselines(daily)
    if len(ordered) < 2:
        return None, "Fewer than two UTC-day equity baselines are stored."
    previous, current = ordered[-2], ordered[-1]
    return current.last_equity - previous.last_equity, _change_detail(previous, current)


def daily_changes(daily: tuple[DailyBaseline, ...]) -> tuple[tuple[date, date, Decimal, str], ...]:
    ordered = ordered_baselines(daily)
    changes: list[tuple[date, date, Decimal, str]] = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        changes.append(
            (
                current.session_date,
                previous.session_date,
                current.last_equity - previous.last_equity,
                _change_detail(previous, current),
            )
        )
    return tuple(changes)


def drawdown_points(
    points: tuple[tuple[date, Decimal], ...],
) -> tuple[tuple[date, Decimal], ...]:
    """Drawdown from the running peak of stored points. No calendar is filled in."""

    if not points:
        return ()
    peak = points[0][1]
    series: list[tuple[date, Decimal]] = []
    for day, value in points:
        if value > peak:
            peak = value
        if peak <= 0:
            continue
        series.append((day, (peak - value) / peak))
    return tuple(series)


def _change_detail(previous: DailyBaseline, current: DailyBaseline) -> str:
    return (
        f"Change in verified equity from {previous.session_date.isoformat()} "
        f"to {current.session_date.isoformat()}. A missing day is not filled with zero."
    )
