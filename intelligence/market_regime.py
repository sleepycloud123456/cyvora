"""A breadth reading for the rank page CYVORA just retrieved.

This is not a GMGN market-regime endpoint. None was verified. The sign of a
rank change is used and the magnitude is not, because Phase 2 did not prove
whether those fields are fractions or percents.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from intelligence.numbers import score


@dataclass(frozen=True, slots=True)
class MarketBreadth:
    """Share of rank rows whose change field is positive."""

    status: str
    score: Decimal | None
    sample_size: int
    positive_count: int
    warnings: tuple[str, ...]


def breadth_from_changes(changes: tuple[Decimal, ...]) -> MarketBreadth:
    """Score breadth only when at least three non-zero changes were present."""

    signed = tuple(change for change in changes if change != 0)
    if len(signed) < 3:
        return MarketBreadth(
            status="missing",
            score=None,
            sample_size=len(signed),
            positive_count=sum(1 for change in signed if change > 0),
            warnings=("Fewer than three rank rows had a non-zero change field.",),
        )
    positive = sum(1 for change in signed if change > 0)
    fraction = Decimal(positive) / Decimal(len(signed))
    return MarketBreadth(
        status="partial",
        score=score(Decimal(20) + (Decimal(60) * fraction)),
        sample_size=len(signed),
        positive_count=positive,
        warnings=(
            "Breadth uses only the sign of GMGN rank changes. The percent scale was not verified.",
        ),
    )
