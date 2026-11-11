"""Decimal helpers for simulation prices. Fees and adverse slippage round away from zero."""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_UP, Decimal

from shield.numbers import quantize_down


def quantize_up(value: Decimal, decimals: int) -> Decimal:
    """Raise extra fractional digits so a cost is not understated."""

    quantum = Decimal(1).scaleb(-decimals)
    return value.quantize(quantum, rounding=ROUND_UP)


def quantize_scale(value: Decimal, decimals: int, *, up: bool) -> Decimal:
    if up:
        return quantize_up(value, decimals)
    return quantize_down(value, decimals)


def fits(value: Decimal, decimals: int) -> bool:
    quantum = Decimal(1).scaleb(-decimals)
    return value == value.quantize(quantum, rounding=ROUND_DOWN)
