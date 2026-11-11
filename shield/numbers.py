"""Decimal rounding for sizes Shield plans. Quantities round down so a plan cannot grow."""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal


def quantize_down(value: Decimal, decimals: int) -> Decimal:
    """Drop extra fractional digits. The result is never larger than ``value``."""

    quantum = Decimal(1).scaleb(-decimals)
    return value.quantize(quantum, rounding=ROUND_DOWN)
