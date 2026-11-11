"""Constant-product pool math.

A buy that spends fraction ``f`` of the quote reserve has impact ``f``.
A sell of fraction ``g`` of the base reserve has impact ``g / (1 + g)``.
Missing reserves are not treated as infinite liquidity.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from domain.exceptions import TradingValidationError


@dataclass(frozen=True)
class PoolFill:
    """One constant-product result before instrument rounding."""

    base_quantity: Decimal
    quote_amount: Decimal
    average_price: Decimal
    spot_price: Decimal
    impact: Decimal


def require_reserves(base_reserve: Decimal | None, quote_reserve: Decimal | None) -> bool:
    if base_reserve is None or quote_reserve is None:
        return False
    return (
        base_reserve > 0
        and quote_reserve > 0
        and base_reserve.is_finite()
        and quote_reserve.is_finite()
    )


def spot_price(base_reserve: Decimal, quote_reserve: Decimal) -> Decimal:
    if base_reserve <= 0 or quote_reserve <= 0:
        raise TradingValidationError("Pool reserves must be positive.")
    return quote_reserve / base_reserve


def max_buy_base(base_reserve: Decimal, quote_reserve: Decimal, quote_spend: Decimal) -> Decimal:
    """Base bought by adding ``quote_spend`` to the pool. Zero spend buys nothing."""

    if quote_spend <= 0:
        return Decimal(0)
    if quote_spend >= quote_reserve * Decimal(1000):
        raise TradingValidationError("The quote spend is too large for this pool.")
    new_quote = quote_reserve + quote_spend
    new_base = (base_reserve * quote_reserve) / new_quote
    return base_reserve - new_base


def max_sell_base(base_reserve: Decimal, impact_cap: Decimal, participation: Decimal) -> Decimal:
    """Largest base sale whose impact stays inside the cap and the participation limit."""

    if impact_cap <= 0 or impact_cap >= 1:
        raise TradingValidationError("Impact cap must be between 0 and 1.")
    if participation <= 0 or participation > 1:
        raise TradingValidationError("Liquidity participation must be between 0 and 1.")
    impact_fraction = impact_cap / (Decimal(1) - impact_cap)
    fraction = min(impact_fraction, participation)
    return base_reserve * fraction


def buy_fill(base_reserve: Decimal, quote_reserve: Decimal, quantity: Decimal) -> PoolFill | None:
    """Price a base buy. A quantity at or above the base reserve does not fill."""

    if quantity <= 0 or quantity >= base_reserve:
        return None
    new_base = base_reserve - quantity
    new_quote = (base_reserve * quote_reserve) / new_base
    quote_in = new_quote - quote_reserve
    average = quote_in / quantity
    spot = spot_price(base_reserve, quote_reserve)
    impact = (average / spot) - Decimal(1)
    return PoolFill(quantity, quote_in, average, spot, impact)


def sell_fill(base_reserve: Decimal, quote_reserve: Decimal, quantity: Decimal) -> PoolFill | None:
    """Price a base sell. The average quote received is below the spot."""

    if quantity <= 0:
        return None
    new_base = base_reserve + quantity
    new_quote = (base_reserve * quote_reserve) / new_base
    quote_out = quote_reserve - new_quote
    if quote_out <= 0:
        return None
    average = quote_out / quantity
    spot = spot_price(base_reserve, quote_reserve)
    if average >= spot:
        return None
    impact = (spot - average) / spot
    return PoolFill(quantity, quote_out, average, spot, impact)
