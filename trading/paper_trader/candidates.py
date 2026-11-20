"""Turn one stored radar analysis into a trader candidate. This does not trade."""

from __future__ import annotations

from decimal import Decimal

from domain.paper_trader import RadarCandidate
from intelligence.numbers import as_decimal


def candidate_from_analysis(
    mint: str,
    symbol: str | None,
    score: Decimal | None,
    lifecycle: str,
    freshness: str,
    security_category: str,
    breakdown: object,
    liquidity: Decimal | None = None,
) -> RadarCandidate:
    """Read price and pool reserves from the analysis breakdown.

    Older cycles have no reserve fields. Those stay missing and cannot fill.
    """

    payload = breakdown if isinstance(breakdown, dict) else {}
    label = symbol.strip() if isinstance(symbol, str) else ""
    return RadarCandidate(
        mint=mint,
        symbol=label or "TOKEN",
        score=score,
        lifecycle=lifecycle,
        freshness=freshness,
        security_category=security_category,
        price=as_decimal(payload.get("price")),
        base_reserve=as_decimal(payload.get("base_reserve")),
        quote_reserve=as_decimal(payload.get("quote_reserve")),
        creation_timestamp=_whole(payload.get("creation_timestamp")),
        liquidity=as_decimal(liquidity)
        if liquidity is not None
        else as_decimal(payload.get("liquidity")),
    )


def _whole(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if text.isdecimal():
            parsed = int(text)
            return parsed if parsed > 0 else None
    return None
