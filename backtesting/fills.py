"""Turn one observation into a paper fill. Candle close is never the fill price."""

from __future__ import annotations

from decimal import Decimal

from backtesting.costs import explicit_zero, fee_quote
from backtesting.liquidity import (
    buy_fill,
    max_buy_base,
    max_sell_base,
    require_reserves,
    sell_fill,
    spot_price,
)
from backtesting.numbers import quantize_down, quantize_up
from domain.simulation import FeeSchedule, FillModel, FillPlan, HistoricalBar
from domain.trading import OrderSide, SolanaInstrument

_IMPACT_SCALE = 8


def price_order(
    bar: HistoricalBar,
    side: OrderSide,
    quantity: Decimal,
    instrument: SolanaInstrument,
    schedule: FeeSchedule,
    *,
    participation: Decimal,
    impact_cap: Decimal,
) -> FillPlan:
    """Price ``quantity`` from reserves or from one displayed book level.

    A bar that only has a close returns an unpriced plan. Impact is omitted
    rather than stored as zero when the model cannot calculate it.
    """

    if quantity <= 0:
        return _refused("quantity_not_positive")
    quantity = quantize_down(quantity, instrument.size_decimals)
    if quantity <= 0:
        return _refused("quantity_below_precision")
    limitations: list[str] = []
    if bar.volume_quote is not None and bar.base_volume is None:
        limitations.append("candle_volume_was_not_used_as_base_size")
    if bar.close is not None:
        limitations.append("candle_close_is_a_mark_not_a_fill")
    if require_reserves(bar.base_reserve, bar.quote_reserve):
        assert bar.base_reserve is not None and bar.quote_reserve is not None
        return _pool(
            bar.base_reserve,
            bar.quote_reserve,
            bar,
            side,
            quantity,
            instrument,
            schedule,
            participation=participation,
            impact_cap=impact_cap,
            limitations=tuple(limitations),
        )
    if _book_ready(bar, side):
        limitations.append("displayed_depth_is_not_a_constant_product_pool")
        return _book(
            bar,
            side,
            quantity,
            instrument,
            schedule,
            participation=participation,
            impact_cap=impact_cap,
            limitations=tuple(limitations),
        )
    limitations.append("pool_reserves_missing")
    return _refused("candle_is_not_a_fill", limitations=tuple(limitations))


def _pool(
    base_reserve: Decimal,
    quote_reserve: Decimal,
    bar: HistoricalBar,
    side: OrderSide,
    quantity: Decimal,
    instrument: SolanaInstrument,
    schedule: FeeSchedule,
    *,
    participation: Decimal,
    impact_cap: Decimal,
    limitations: tuple[str, ...],
) -> FillPlan:
    spend_cap = min(participation, impact_cap) * quote_reserve
    if side is OrderSide.BUY:
        room = quantize_down(
            max_buy_base(base_reserve, quote_reserve, spend_cap), instrument.size_decimals
        )
        fill = buy_fill(base_reserve, quote_reserve, min(quantity, room))
    else:
        room = quantize_down(
            max_sell_base(base_reserve, impact_cap, participation), instrument.size_decimals
        )
        fill = sell_fill(base_reserve, quote_reserve, min(quantity, room))
    if fill is None or room <= 0:
        return _refused("insufficient_liquidity", limitations=limitations)
    sized = min(quantity, room)
    if sized != fill.base_quantity:
        return _refused("insufficient_liquidity", limitations=limitations)
    partial = sized < quantity
    worse_than_book = _worse_quote(side, fill.average_price, bar)
    return _from_prices(
        side=side,
        quantity=sized,
        partial=partial,
        spot=fill.spot_price,
        execution=worse_than_book,
        impact=fill.impact
        if worse_than_book == fill.average_price
        else _distance_impact(fill.spot_price, worse_than_book),
        liquidity_quote=quote_reserve,
        model=FillModel.CONSTANT_PRODUCT.value,
        instrument=instrument,
        schedule=schedule,
        impact_cap=impact_cap,
        limitations=limitations,
    )


def _book(
    bar: HistoricalBar,
    side: OrderSide,
    quantity: Decimal,
    instrument: SolanaInstrument,
    schedule: FeeSchedule,
    *,
    participation: Decimal,
    impact_cap: Decimal,
    limitations: tuple[str, ...],
) -> FillPlan:
    bid = bar.bid if bar.bid is not None else Decimal(0)
    ask = bar.ask if bar.ask is not None else Decimal(0)
    if bid <= 0 or ask <= 0 or ask < bid:
        return _refused("book_not_usable", limitations=limitations)
    mid = (bid + ask) / 2
    if side is OrderSide.BUY:
        shown = bar.ask_size or Decimal(0)
        execution = ask
        liquidity = ask * shown
    else:
        shown = bar.bid_size or Decimal(0)
        execution = bid
        liquidity = bid * shown
    capped = quantize_down(shown * participation, instrument.size_decimals)
    if capped <= 0 or liquidity <= 0:
        return _refused("insufficient_liquidity", limitations=limitations)
    sized = min(quantity, capped)
    impact = _distance_impact(mid, execution)
    if impact > impact_cap:
        return _refused(
            "impact_above_cap", limitations=limitations + ("spread_is_not_reduced_to_zero",)
        )
    return _from_prices(
        side=side,
        quantity=sized,
        partial=sized < quantity,
        spot=mid,
        execution=execution,
        impact=impact,
        liquidity_quote=liquidity,
        model=FillModel.DISPLAYED_DEPTH.value,
        instrument=instrument,
        schedule=schedule,
        impact_cap=impact_cap,
        limitations=limitations,
    )


def _from_prices(
    *,
    side: OrderSide,
    quantity: Decimal,
    partial: bool,
    spot: Decimal,
    execution: Decimal,
    impact: Decimal,
    liquidity_quote: Decimal,
    model: str,
    instrument: SolanaInstrument,
    schedule: FeeSchedule,
    impact_cap: Decimal,
    limitations: tuple[str, ...],
) -> FillPlan:
    scale = min(instrument.price_decimals, instrument.quote_decimals)
    reference = quantize_down(spot, instrument.price_decimals)
    if side is OrderSide.BUY:
        executed = quantize_up(execution, scale)
        if executed < reference:
            executed = reference
        slippage = quantize_up(executed - reference, scale)
        executed = reference + slippage
    else:
        executed = quantize_down(execution, scale)
        if executed > reference:
            executed = reference
        slippage = quantize_up(reference - executed, scale)
        executed = reference - slippage
    if executed <= 0 or reference <= 0:
        return _refused("fill_price_not_positive", limitations=limitations)
    reported_impact = quantize_up(impact, _IMPACT_SCALE)
    if reported_impact > impact_cap:
        return _refused("impact_above_cap", limitations=limitations)
    notional = executed * quantity
    fee = fee_quote(schedule, notional, instrument.quote_decimals)
    notes = limitations
    if explicit_zero(schedule):
        notes = notes + ("explicit_zero_fee",)
    if partial:
        notes = notes + ("participation_capped_the_fill",)
    if quantity <= 0:
        return _refused("quantity_below_precision", limitations=notes)
    return FillPlan(
        True,
        None,
        model,
        "FILL",
        quantity,
        reference,
        slippage,
        fee,
        reported_impact,
        liquidity_quote,
        notes,
    )


def _worse_quote(side: OrderSide, average: Decimal, bar: HistoricalBar) -> Decimal:
    if side is OrderSide.BUY and bar.ask is not None and bar.ask > average:
        return bar.ask
    if side is OrderSide.SELL and bar.bid is not None and bar.bid < average:
        return bar.bid
    return average


def _distance_impact(reference: Decimal, execution: Decimal) -> Decimal:
    if reference <= 0:
        return Decimal(1)
    return abs(execution - reference) / reference


def _book_ready(bar: HistoricalBar, side: OrderSide) -> bool:
    del side
    return (
        bar.bid is not None
        and bar.ask is not None
        and bar.bid_size is not None
        and bar.ask_size is not None
    )


def _refused(reason: str, limitations: tuple[str, ...] = ()) -> FillPlan:
    return FillPlan(False, reason, None, None, None, None, None, None, None, None, limitations)


def pool_spot(bar: HistoricalBar) -> Decimal | None:
    if not require_reserves(bar.base_reserve, bar.quote_reserve):
        return None
    assert bar.base_reserve is not None and bar.quote_reserve is not None
    return spot_price(bar.base_reserve, bar.quote_reserve)
