"""Average price, cost, and realized result for one paper position."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from domain.exceptions import TradingValidationError
from domain.trading import OrderSide, PositionRecord


def apply_fill(
    position: PositionRecord | None,
    *,
    mint: str,
    side: OrderSide,
    filled_quantity: Decimal,
    fill_price: Decimal,
    fee_quote: Decimal,
    quote_symbol: str,
    now: datetime,
) -> PositionRecord:
    """Apply one simulated fill.

    A buy adds the quote fee to cost. A sell subtracts the quote fee from
    realized result. The average price is cost divided by open quantity.
    """

    if position is not None and position.quote_symbol != quote_symbol:
        raise TradingValidationError("The open position uses a different quote symbol.")
    if position is not None and position.mint != mint:
        raise TradingValidationError("The fill mint does not match the position.")

    quantity = Decimal(0) if position is None else position.quantity
    cost = Decimal(0) if position is None else position.cost_quote
    realized = Decimal(0) if position is None else position.realized_pnl_quote

    if side is OrderSide.BUY:
        quantity += filled_quantity
        cost += (fill_price * filled_quantity) + fee_quote
        average: Decimal | None = cost / quantity
    else:
        if position is None or filled_quantity > position.quantity:
            raise TradingValidationError("The simulated sell is larger than the open position.")
        average_before = position.average_price
        if average_before is None:
            raise TradingValidationError("The open position has no average price.")
        realized += ((fill_price - average_before) * filled_quantity) - fee_quote
        quantity -= filled_quantity
        if quantity == 0:
            cost = Decimal(0)
            average = None
        else:
            cost = average_before * quantity
            average = average_before

    return PositionRecord(
        mint=mint,
        quantity=quantity,
        average_price=average,
        cost_quote=cost,
        realized_pnl_quote=realized,
        quote_symbol=quote_symbol,
        updated_at=now,
    )


def unrealized_pnl(position: PositionRecord, mark_price: Decimal | None) -> Decimal | None:
    """Value the open quantity at a supplied mark. A missing mark stays missing."""

    if position.quantity == 0 or position.average_price is None:
        return Decimal(0) if position.quantity == 0 else None
    if mark_price is None:
        return None
    return (mark_price - position.average_price) * position.quantity
