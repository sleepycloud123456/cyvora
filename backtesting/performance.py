"""Performance measured from a finished paper book. Small samples do not get a Sharpe ratio."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from domain.shield import CampaignRecord
from domain.simulation import PerformanceReport
from domain.trading import OrderRecord

_MIN_RETURNS = 30
_RATIO = Decimal("0.00000001")


def measure(
    *,
    orders: tuple[OrderRecord, ...],
    campaigns: tuple[CampaignRecord, ...],
    strategy_id: str,
    starting_equity: Decimal,
    ending_equity: Decimal | None,
    equity_curve: tuple[Decimal, ...],
    bars_in_market: int,
    bar_count: int,
) -> PerformanceReport:
    """Score one isolated paper book. Open campaigns stay out of the win rate."""

    closed = tuple(item for item in campaigns if item.closed_at is not None)
    wins = tuple(item.net_pnl_quote for item in closed if item.net_pnl_quote > 0)
    losses = tuple(item.net_pnl_quote for item in closed if item.net_pnl_quote < 0)
    gross_profit = sum(wins, Decimal(0))
    gross_loss = sum((-item for item in losses), Decimal(0))
    limitations: list[str] = []
    if any(item.closed_at is None for item in campaigns):
        limitations.append("open_position_excluded_from_win_rate")
    net = None if ending_equity is None else ending_equity - starting_equity
    total = None
    if net is not None and starting_equity > 0:
        total = net / starting_equity
    elif net is not None:
        limitations.append("starting_equity_not_positive")
    win_rate = None if not closed else Decimal(len(wins)) / Decimal(len(closed))
    average_win = None if not wins else gross_profit / Decimal(len(wins))
    average_loss = None if not losses else gross_loss / Decimal(len(losses))
    profit_factor = None
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif closed:
        limitations.append("profit_factor_undefined")
    drawdown = _drawdown(equity_curve)
    risk_adjusted = None
    if net is not None and drawdown is not None and drawdown > 0:
        risk_adjusted = net / drawdown
    elif net is not None:
        limitations.append("no_drawdown")
    sharpe, sharpe_reason, sortino, sortino_reason = _ratios(_returns(equity_curve))
    holding = _holding(closed)
    fees = sum((order.fee_quote for order in orders if order.filled_quantity > 0), Decimal(0))
    exposure = None
    if bar_count > 0:
        exposure = Decimal(bars_in_market) / Decimal(bar_count)
    contribution = () if net is None else ((strategy_id, net),)
    return PerformanceReport(
        total_return=total,
        net_profit=net,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        win_rate=win_rate,
        average_win=average_win,
        average_loss=average_loss,
        profit_factor=profit_factor,
        max_drawdown=drawdown,
        sharpe=sharpe,
        sharpe_reason=sharpe_reason,
        sortino=sortino,
        sortino_reason=sortino_reason,
        average_holding_seconds=holding,
        trade_count=len(closed),
        order_count=len(orders),
        exposure=exposure,
        fees=fees,
        strategy_contribution=contribution,
        risk_adjusted=risk_adjusted,
        limitations=tuple(limitations),
    )


def _drawdown(curve: tuple[Decimal, ...]) -> Decimal | None:
    if not curve:
        return None
    peak = curve[0]
    worst = Decimal(0)
    for value in curve:
        if value > peak:
            peak = value
        if peak > 0:
            drop = (peak - value) / peak
            if drop > worst:
                worst = drop
    return worst


def _returns(curve: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    results: list[Decimal] = []
    for earlier, later in zip(curve, curve[1:], strict=False):
        if earlier > 0:
            results.append((later - earlier) / earlier)
    return tuple(results)


def _ratios(
    returns: tuple[Decimal, ...],
) -> tuple[Decimal | None, str | None, Decimal | None, str | None]:
    if len(returns) < _MIN_RETURNS:
        reason = "not_statistically_meaningful"
        return None, reason, None, reason
    count = Decimal(len(returns))
    mean = sum(returns, Decimal(0)) / count
    variance = sum(((item - mean) ** 2 for item in returns), Decimal(0)) / (count - 1)
    if variance == 0:
        sharpe, sharpe_reason = None, "zero_variance"
    else:
        sharpe, sharpe_reason = _round(mean / variance.sqrt()), None
    downside = sum((min(item, Decimal(0)) ** 2 for item in returns), Decimal(0)) / (count - 1)
    if downside == 0:
        sortino, sortino_reason = None, "no_downside"
    else:
        sortino, sortino_reason = _round(mean / downside.sqrt()), None
    return sharpe, sharpe_reason, sortino, sortino_reason


def _holding(campaigns: tuple[CampaignRecord, ...]) -> Decimal | None:
    if not campaigns:
        return None
    total = Decimal(0)
    for campaign in campaigns:
        closed_at = campaign.closed_at
        opened_at = campaign.opened_at
        if closed_at is None:
            continue
        total += Decimal(_elapsed(opened_at, closed_at))
    return total / Decimal(len(campaigns))


def _elapsed(opened: datetime, closed: datetime) -> int:
    return int((closed - opened).total_seconds())


def _round(value: Decimal) -> Decimal:
    return value.quantize(_RATIO)
