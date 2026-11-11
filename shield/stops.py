"""Stop, take-profit, and trailing-stop calculations.

A planned stop is the price used for the risk budget. It is not an exit that
the market is required to honor.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

from domain.shield import ShieldLimits, StopPlan, TakeProfitSlice
from shield.numbers import quantize_down


def propose_stop(
    expected_fill: Decimal,
    volatility: Decimal,
    *,
    equity: Decimal,
    liquidity_quote: Decimal | None,
    token_age_seconds: int | None,
    market_condition: str | None,
    slippage_quote: Decimal,
    limits: ShieldLimits,
) -> tuple[Decimal, tuple[str, ...]]:
    """Widen a volatility distance. Missing age or liquidity is skipped, not invented."""

    notes: list[str] = []
    distance = volatility * limits.volatility_multiplier
    if liquidity_quote is None:
        notes.append("liquidity_not_used_for_stop")
    elif equity > 0:
        depth_ratio = liquidity_quote / equity
        if depth_ratio < limits.liquidity_widen_below:
            widen = (limits.liquidity_widen_below - depth_ratio) / limits.liquidity_widen_below
            distance *= Decimal(1) + widen
            notes.append("liquidity_widened")
    if token_age_seconds is None:
        notes.append("token_age_not_supplied")
    elif token_age_seconds < limits.young_token_seconds:
        distance *= limits.young_token_multiplier
        notes.append("young_token_widened")
    if market_condition is None:
        notes.append("market_condition_not_supplied")
    elif market_condition == "stressed":
        distance *= limits.stressed_multiplier
        notes.append("stressed_widened")
    distance += slippage_quote
    return expected_fill - distance, tuple(notes)


def plan_take_profits(
    quantity: Decimal,
    limits: ShieldLimits,
    size_decimals: int,
) -> tuple[TakeProfitSlice, ...]:
    """Split a position. Rounding down keeps the planned total at or below the quantity."""

    remaining = quantity
    slices: list[TakeProfitSlice] = []
    for level in limits.take_profit_levels:
        planned = quantize_down(quantity * level.quantity_fraction, size_decimals)
        if planned > remaining:
            planned = remaining
        remaining -= planned
        slices.append(
            TakeProfitSlice(
                gain_fraction=level.gain_fraction,
                quantity_fraction=level.quantity_fraction,
                planned_quantity=planned,
                consumed_quantity=Decimal(0),
            )
        )
    return tuple(slices)


def advance_trailing(
    plan: StopPlan,
    mark: Decimal,
    now: datetime,
    volatility: Decimal | None,
    limits: ShieldLimits,
) -> tuple[StopPlan, str]:
    """Move a long stop up. The stop never loosens, and trail updates wait for the interval."""

    if plan.entry_price <= 0:
        return plan, "unchanged"
    gain = (mark - plan.entry_price) / plan.entry_price
    peak = mark if mark > plan.peak_price else plan.peak_price
    stop = plan.stop_price
    if gain >= limits.break_even_fraction and plan.average_price > stop:
        stop = plan.average_price
    if gain < limits.trail_activation_fraction:
        return replace(plan, peak_price=peak, stop_price=stop), "not_activated"
    if plan.last_trail_at is not None and now - plan.last_trail_at < timedelta(
        seconds=limits.trail_min_interval_seconds
    ):
        return replace(plan, peak_price=peak, stop_price=stop), "update_interval"
    distance = mark * limits.trail_distance_fraction
    if volatility is not None and volatility > 0:
        vol_distance = volatility * limits.volatility_multiplier
        if vol_distance > distance:
            distance = vol_distance
    trailed = mark - distance
    new_stop = trailed if trailed > stop else stop
    raised = new_stop > plan.stop_price
    return (
        replace(
            plan,
            peak_price=peak,
            stop_price=new_stop,
            trailing_active=True,
            last_trail_at=now if raised else plan.last_trail_at,
        ),
        "raised" if raised else "unchanged",
    )
