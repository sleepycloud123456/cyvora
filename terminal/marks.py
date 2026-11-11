"""Stored price marks. Candle close is labeled as a mark and is not a fill."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from intelligence.numbers import as_decimal
from intelligence.store import CycleSnapshot


@dataclass(frozen=True)
class Mark:
    """One stored price and where it came from."""

    price: Decimal
    source: str
    observed_at: str | None


def marks_for(cycle: CycleSnapshot | None) -> dict[str, Mark]:
    """Prefer the stored ranking price. Otherwise use the last stored candle close."""

    if cycle is None:
        return {}
    found: dict[str, Mark] = {}
    observed = cycle.finished_at
    for row in cycle.rankings:
        price = as_decimal(row.price)
        if price is None or price <= 0:
            continue
        found[row.address] = Mark(price, f"radar cycle {cycle.cycle_id} ranking", observed)
    for detail in cycle.analyses:
        if detail.address in found:
            continue
        close = _last_close(detail.candles)
        if close is None:
            continue
        found[detail.address] = Mark(
            close,
            f"radar cycle {cycle.cycle_id} candle close (mark, not a fill)",
            observed,
        )
    return found


def _last_close(
    candles: tuple[tuple[int | None, str | None, str | None, str | None, str | None], ...],
) -> Decimal | None:
    for candle in reversed(candles):
        close = as_decimal(candle[4])
        if close is not None and close > 0:
            return close
    return None
