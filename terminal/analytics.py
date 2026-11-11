"""Analytics from stored equity, closed campaigns, and undeployed research runs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal

from backtesting.performance import peak_drawdown, risk_ratios
from domain.shield import CampaignRecord, DailyBaseline
from domain.terminal import (
    AnalyticsView,
    DailyPnl,
    PeriodPnl,
    ResearchComparison,
    StrategyPerformance,
    TokenPerformance,
)
from domain.trading import OrderRecord
from intelligence.numbers import as_decimal
from terminal.equity import daily_changes, drawdown_points, equity_points


def build_analytics(
    orders: tuple[OrderRecord, ...],
    campaigns: tuple[CampaignRecord, ...],
    daily: tuple[DailyBaseline, ...],
    reports: tuple[Mapping[str, object], ...],
) -> AnalyticsView:
    """Measure what is stored. Research rows stay separate from the operator book."""

    points = equity_points(daily)
    changes = daily_changes(daily)
    closed = tuple(
        item
        for item in campaigns
        if item.closed_at is not None and item.closed_at >= item.opened_at
    )
    skipped_time = any(
        item.closed_at is not None and item.closed_at < item.opened_at for item in campaigns
    )
    wins = tuple(item for item in closed if item.net_pnl_quote > 0)
    losses = tuple(item for item in closed if item.net_pnl_quote < 0)
    flats = len(closed) - len(wins) - len(losses)
    curve = tuple(value for _day, value in points)
    returns = _returns(curve)
    sharpe, sharpe_reason, sortino, sortino_reason = risk_ratios(returns)
    limitations: list[str] = []
    if len(points) < 2:
        limitations.append("equity_curve_needs_two_stored_points")
        sharpe, sharpe_reason = None, "no_equity_curve"
        sortino, sortino_reason = None, "no_equity_curve"
    if any(earlier <= 0 for earlier, _later in zip(curve, curve[1:], strict=False)):
        limitations.append("non_positive_equity_omitted_from_returns")
    if skipped_time:
        limitations.append("negative_holding_omitted")
    if any(item.closed_at is None for item in campaigns):
        limitations.append("open_position_excluded_from_win_rate")
    drawdown = peak_drawdown(curve)
    net = None if len(points) < 2 else points[-1][1] - points[0][1]
    risk_adjusted = None
    if net is not None and drawdown is not None and drawdown > 0:
        risk_adjusted = net / drawdown
    elif net is not None:
        limitations.append("no_drawdown")
    fees = sum((order.fee_quote for order in orders if order.filled_quantity > 0), Decimal(0))
    holding, holding_detail = _holding(closed)
    return AnalyticsView(
        equity_points=points,
        drawdown_points=drawdown_points(points),
        daily=tuple(
            DailyPnl(current, previous, value, detail)
            for current, previous, value, detail in changes
        ),
        weekly=_periods(changes, _week),
        monthly=_periods(changes, _month),
        wins=len(wins),
        losses=len(losses),
        flats=flats,
        profit_values=tuple(item.net_pnl_quote for item in closed),
        average_holding_seconds=holding,
        holding_detail=holding_detail,
        strategies=_strategies(closed),
        tokens=_tokens(closed),
        research=_research(reports),
        sharpe=sharpe,
        sharpe_reason=sharpe_reason,
        sortino=sortino,
        sortino_reason=sortino_reason,
        risk_adjusted=risk_adjusted,
        net_profit=net,
        fees=fees,
        limitations=tuple(limitations),
    )


def _returns(curve: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    results: list[Decimal] = []
    for earlier, later in zip(curve, curve[1:], strict=False):
        if earlier > 0:
            results.append((later - earlier) / earlier)
    return tuple(results)


def _holding(closed: tuple[CampaignRecord, ...]) -> tuple[Decimal | None, str]:
    if not closed:
        return None, "No closed paper campaign is stored."
    total = Decimal(0)
    for campaign in closed:
        closed_at = campaign.closed_at
        if closed_at is None:
            continue
        total += Decimal(int((closed_at - campaign.opened_at).total_seconds()))
    average = total / Decimal(len(closed))
    return average, "Mean time from campaign open to close. Open campaigns are excluded."


def _strategies(closed: tuple[CampaignRecord, ...]) -> tuple[StrategyPerformance, ...]:
    grouped: dict[str, list[CampaignRecord]] = defaultdict(list)
    for campaign in closed:
        grouped[campaign.strategy_id].append(campaign)
    rows: list[StrategyPerformance] = []
    for strategy_id in sorted(grouped):
        items = grouped[strategy_id]
        wins = [item.net_pnl_quote for item in items if item.net_pnl_quote > 0]
        losses = [item.net_pnl_quote for item in items if item.net_pnl_quote < 0]
        gross_profit = sum(wins, Decimal(0))
        gross_loss = sum((-item for item in losses), Decimal(0))
        factor = None if gross_loss <= 0 else gross_profit / gross_loss
        rate = None if not items else Decimal(len(wins)) / Decimal(len(items))
        rows.append(
            StrategyPerformance(
                strategy_id,
                len(items),
                sum((item.net_pnl_quote for item in items), Decimal(0)),
                rate,
                factor,
            )
        )
    return tuple(rows)


def _tokens(closed: tuple[CampaignRecord, ...]) -> tuple[TokenPerformance, ...]:
    grouped: dict[str, list[CampaignRecord]] = defaultdict(list)
    for campaign in closed:
        grouped[campaign.mint].append(campaign)
    return tuple(
        TokenPerformance(
            mint,
            sum((item.net_pnl_quote for item in grouped[mint]), Decimal(0)),
            len(grouped[mint]),
        )
        for mint in sorted(grouped)
    )


def _periods(
    changes: tuple[tuple[date, date, Decimal, str], ...],
    label_for: Callable[[date], str],
) -> tuple[PeriodPnl, ...]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for current, _previous, value, _detail in changes:
        totals[label_for(current)] += value
    return tuple(PeriodPnl(label, totals[label]) for label in sorted(totals))


def _week(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _month(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _research(reports: tuple[Mapping[str, object], ...]) -> tuple[ResearchComparison, ...]:
    rows: list[ResearchComparison] = []
    for payload in reports:
        if payload.get("parameters_deployed") is not False:
            continue
        run_id = payload.get("run_id")
        kind = payload.get("kind")
        if not isinstance(run_id, str) or not isinstance(kind, str):
            continue
        strategies = payload.get("strategies")
        if isinstance(strategies, list) and strategies:
            for item in strategies:
                parsed = _strategy_row(run_id, kind, item)
                if parsed is not None:
                    rows.append(parsed)
            continue
        strategy_id = payload.get("strategy_id")
        if not isinstance(strategy_id, str):
            continue
        performance = payload.get("performance")
        net = None
        trades = None
        drawdown = None
        if isinstance(performance, dict):
            net = as_decimal(performance.get("net_profit"))
            drawdown = as_decimal(performance.get("max_drawdown"))
            count = performance.get("trade_count")
            trades = count if isinstance(count, int) else None
        rows.append(
            ResearchComparison(
                run_id,
                kind,
                strategy_id,
                strategy_id,
                net,
                trades,
                drawdown,
                False,
            )
        )
    return tuple(rows)


def _strategy_row(run_id: str, kind: str, item: object) -> ResearchComparison | None:
    if not isinstance(item, dict):
        return None
    strategy_id = item.get("strategy_id")
    if not isinstance(strategy_id, str):
        return None
    name = item.get("name")
    count = item.get("trade_count")
    return ResearchComparison(
        run_id,
        kind,
        strategy_id,
        name if isinstance(name, str) else strategy_id,
        as_decimal(item.get("net_profit")),
        count if isinstance(count, int) else None,
        as_decimal(item.get("max_drawdown")),
        False,
    )
