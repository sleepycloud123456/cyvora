"""Paper portfolio figures from stored positions, Shield, and radar marks."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from domain.shield import CampaignRecord, ShieldSnapshot
from domain.terminal import PortfolioView, PositionLine, RecentOrder
from domain.trading import OrderRecord, PositionRecord, StrategyState, TradingSnapshot
from intelligence.numbers import format_decimal
from terminal.equity import drawdown_points, equity_points, latest_daily_change
from terminal.marks import Mark
from trading.portfolio.accounting import unrealized_pnl

_NO_WALLET = "No wallet is connected. This is not a SOL balance."
_NO_USD = "No USD conversion is stored."


def build_portfolio(
    trading: TradingSnapshot,
    shield: ShieldSnapshot,
    marks: dict[str, Mark],
    *,
    now: datetime,
) -> PortfolioView:
    """Summarize the paper book. Missing marks and mixed quotes are not summed."""

    open_rows = tuple(row for row in trading.positions if row.quantity > 0)
    quotes = {row.quote_symbol for row in trading.positions}
    open_quotes = {row.quote_symbol for row in open_rows}
    realized, realized_unit, realized_detail = _realized(trading.positions, quotes)
    allocated, allocated_unit, allocated_detail = _allocated(open_rows, open_quotes)
    lines = tuple(_line(row, trading.orders, shield, marks, now) for row in open_rows)
    unrealized, unrealized_detail = _unrealized(lines)
    verified, verified_detail = _verified(shield)
    marked = _marked_value(lines, open_quotes)
    available, available_detail = _available(verified, marked, open_rows, open_quotes)
    total, total_detail = _total(realized, realized_unit, unrealized, unrealized_detail)
    daily, daily_detail = latest_daily_change(shield.daily)
    points = equity_points(shield.daily)
    drawdown = _max_drawdown(points)
    exposure, exposure_detail = _exposure(verified, marked, allocated, allocated_unit, open_quotes)
    wins = _closed(shield.campaigns)
    win_rate, win_detail = _win_rate(wins)
    average, average_detail = _average(wins)
    recent = tuple(
        RecentOrder(
            order.client_order_id,
            order.symbol,
            order.side.value,
            order.state.value,
            order.shield_decision,
            order.updated_at,
        )
        for order in sorted(trading.orders, key=lambda item: item.updated_at, reverse=True)[:8]
    )
    return PortfolioView(
        verified_equity=verified,
        verified_equity_detail=verified_detail,
        sol_balance_detail=_NO_WALLET,
        usd_detail=_NO_USD,
        allocated=allocated,
        allocated_unit=allocated_unit,
        allocated_detail=allocated_detail,
        available=available,
        available_detail=available_detail,
        open_positions=len(open_rows),
        unrealized=unrealized,
        unrealized_detail=unrealized_detail,
        realized=realized,
        realized_unit=realized_unit,
        realized_detail=realized_detail,
        daily_pnl=daily,
        daily_pnl_detail=daily_detail,
        total_pnl=total,
        total_pnl_detail=total_detail,
        win_rate=win_rate,
        win_rate_detail=win_detail,
        average_profit=average,
        average_profit_detail=average_detail,
        active_strategies=sum(
            1 for strategy in trading.strategies if strategy.state is StrategyState.RUNNING
        ),
        market_condition="not stored",
        market_detail="The latest radar cycle does not store a market-condition label.",
        risk_status=_risk_state(shield),
        risk_detail=_risk_detail(shield),
        exposure=exposure,
        exposure_detail=exposure_detail,
        max_drawdown=drawdown[0],
        drawdown_detail=drawdown[1],
        sol_reserve_fraction=shield.limits.min_sol_reserve_fraction,
        sol_reserve_detail=_reserve_detail(shield, verified),
        recent=recent,
        positions=lines,
    )


def _line(
    position: PositionRecord,
    orders: tuple[OrderRecord, ...],
    shield: ShieldSnapshot,
    marks: dict[str, Mark],
    now: datetime,
) -> PositionLine:
    mark = marks.get(position.mint)
    price = None if mark is None else mark.price
    value = None if price is None else price * position.quantity
    plan = next((item for item in shield.stops if item.mint == position.mint), None)
    campaign = next(
        (
            item
            for item in shield.campaigns
            if item.mint == position.mint and item.closed_at is None
        ),
        None,
    )
    related = [order for order in orders if order.mint == position.mint]
    related.sort(key=lambda item: item.updated_at, reverse=True)
    symbol = related[0].symbol if related else position.mint
    strategy_id = campaign.strategy_id if campaign is not None else None
    if strategy_id is None and related:
        strategy_id = related[0].strategy_id
    holding = None
    if campaign is not None:
        elapsed = int((now - campaign.opened_at).total_seconds())
        holding = elapsed if elapsed >= 0 else None
    take_profits = "No stop plan is stored."
    stop_price = None
    trailing = None
    if plan is not None:
        stop_price = plan.stop_price
        trailing = plan.trailing_active
        if plan.levels:
            parts = []
            for level in plan.levels:
                gain = format_decimal(level.gain_fraction) or "none"
                planned = format_decimal(level.planned_quantity) or "none"
                consumed = format_decimal(level.consumed_quantity) or "none"
                parts.append(f"gain {gain} planned {planned} consumed {consumed}")
            take_profits = "; ".join(parts)
        else:
            take_profits = "The stop plan has no take-profit level."
    return PositionLine(
        mint=position.mint,
        symbol=symbol,
        quantity=position.quantity,
        entry_price=position.average_price,
        current_price=price,
        price_source=None if mark is None else mark.source,
        price_observed_at=None if mark is None else mark.observed_at,
        position_value=value,
        unrealized_pnl=unrealized_pnl(position, price),
        stop_price=stop_price,
        trailing_active=trailing,
        take_profits=take_profits,
        holding_seconds=holding,
        strategy_id=strategy_id,
        risk_level=campaign.security if campaign is not None else "not stored",
        quote_symbol=position.quote_symbol,
    )


def _realized(
    positions: tuple[PositionRecord, ...], quotes: set[str]
) -> tuple[Decimal | None, str | None, str]:
    if not positions:
        return Decimal(0), None, "No position rows are stored."
    if len(quotes) != 1:
        listed = ", ".join(sorted(quotes))
        return (
            None,
            None,
            f"Realized results use more than one quote ({listed}) and are not summed.",
        )
    unit = next(iter(quotes))
    total = sum((row.realized_pnl_quote for row in positions), Decimal(0))
    return total, unit, f"Lifetime realized result stored on paper positions, in {unit}."


def _allocated(
    positions: tuple[PositionRecord, ...], quotes: set[str]
) -> tuple[Decimal | None, str | None, str]:
    if not positions:
        return Decimal(0), None, "No open paper position is stored."
    if len(quotes) != 1:
        listed = ", ".join(sorted(quotes))
        return None, None, f"Open positions use more than one quote ({listed}) and are not summed."
    unit = next(iter(quotes))
    total = sum((row.cost_quote for row in positions), Decimal(0))
    return total, unit, f"Open cost stored on paper positions, in {unit}."


def _unrealized(lines: tuple[PositionLine, ...]) -> tuple[Decimal | None, str]:
    if not lines:
        return Decimal(0), "No open paper position is stored."
    missing = [line.symbol for line in lines if line.unrealized_pnl is None]
    if missing:
        return None, "Unrealized result is missing a stored mark for " + ", ".join(missing) + "."
    total = sum((line.unrealized_pnl or Decimal(0) for line in lines), Decimal(0))
    return total, "Marked from stored radar prices. A mark is not a fill."


def _verified(shield: ShieldSnapshot) -> tuple[Decimal | None, str]:
    if not shield.daily:
        return None, "No verified paper equity is stored."
    current = max(shield.daily, key=lambda row: row.session_date)
    return (
        current.last_equity,
        f"Shield verified equity for UTC {current.session_date.isoformat()}. "
        "It is not a wallet balance.",
    )


def _marked_value(lines: tuple[PositionLine, ...], quotes: set[str]) -> Decimal | None:
    if len(quotes) != 1 or next(iter(quotes), "SOL") != "SOL":
        return None
    if any(line.position_value is None for line in lines):
        return None
    return sum((line.position_value or Decimal(0) for line in lines), Decimal(0))


def _available(
    equity: Decimal | None,
    marked: Decimal | None,
    positions: tuple[PositionRecord, ...],
    quotes: set[str],
) -> tuple[Decimal | None, str]:
    if equity is None:
        return None, "Available capital needs a verified paper equity, which is not stored."
    if not positions:
        return equity, (
            "No open position is stored, so this is the last verified equity. "
            "It is not a wallet SOL balance."
        )
    if quotes != {"SOL"}:
        return None, "Available capital is not derived when open positions are not quoted in SOL."
    if marked is None:
        return None, "Available capital needs a stored mark for every open SOL position."
    return equity - marked, (
        "Last verified equity minus the current marked value of open positions. "
        "Those times can differ. This is not a wallet balance."
    )


def _total(
    realized: Decimal | None,
    unit: str | None,
    unrealized: Decimal | None,
    unrealized_detail: str,
) -> tuple[Decimal | None, str]:
    if realized is None:
        return None, "Total result is not summed across quotes."
    if unrealized is None:
        return None, unrealized_detail
    unit_text = unit or "quote"
    return realized + unrealized, (
        f"Stored realized result plus marked unrealized result, in {unit_text}. "
        "It is not a wallet profit."
    )


def _max_drawdown(points: tuple[tuple[date, Decimal], ...]) -> tuple[Decimal | None, str]:
    series = drawdown_points(points)
    if len(points) < 2:
        return None, "At least two verified equity points are required for drawdown."
    if not series:
        return None, "Drawdown is not computed when verified equity is not positive."
    worst = max(value for _day, value in series)
    return worst, "Drop from the running peak of stored verified-equity points."


def _exposure(
    equity: Decimal | None,
    marked: Decimal | None,
    allocated: Decimal | None,
    unit: str | None,
    quotes: set[str],
) -> tuple[Decimal | None, str]:
    if equity is None or equity <= 0:
        return None, "Exposure needs a positive verified paper equity."
    if quotes and quotes != {"SOL"}:
        return None, "Exposure is not derived when open positions are not quoted in SOL."
    if marked is not None:
        return marked / equity, "Marked open value divided by the last verified equity."
    if allocated is not None and unit == "SOL":
        return (
            allocated / equity,
            "Open cost divided by the last verified equity. Cost is not a mark.",
        )
    if not quotes:
        return Decimal(0), "No open position is stored."
    return None, "Exposure needs either a complete mark or stored SOL cost."


def _closed(campaigns: tuple[CampaignRecord, ...]) -> tuple[CampaignRecord, ...]:
    return tuple(item for item in campaigns if item.closed_at is not None)


def _win_rate(closed: tuple[CampaignRecord, ...]) -> tuple[Decimal | None, str]:
    if not closed:
        return None, "No closed paper campaign is stored."
    wins = sum(1 for item in closed if item.net_pnl_quote > 0)
    return (
        Decimal(wins) / Decimal(len(closed)),
        "Closed paper campaigns. Open campaigns are excluded.",
    )


def _average(closed: tuple[CampaignRecord, ...]) -> tuple[Decimal | None, str]:
    if not closed:
        return None, "No closed paper campaign is stored."
    total = sum((item.net_pnl_quote for item in closed), Decimal(0))
    return total / Decimal(len(closed)), "Mean net result of closed paper campaigns."


def _risk_state(shield: ShieldSnapshot) -> str:
    if shield.breach_latched:
        return "breached"
    if shield.halt_entries:
        return "entries paused"
    return "enforcing"


def _risk_detail(shield: ShieldSnapshot) -> str:
    reasons = ", ".join(shield.breach_reasons) if shield.breach_reasons else "none"
    return (
        f"Live trading is locked. Breach reasons: {reasons}. "
        "A stored denied decision is not an entry."
    )


def _reserve_detail(shield: ShieldSnapshot, equity: Decimal | None) -> str:
    base = (
        "Configured minimum fraction. No wallet SOL balance is connected. "
        "A planned reserve is not cash in a wallet."
    )
    if equity is None:
        return base
    amount = format_decimal(equity * shield.limits.min_sol_reserve_fraction) or "none"
    return base + f" Applied to the last verified equity, the fraction is {amount}."
