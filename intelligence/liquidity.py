"""Liquidity assessment from GMGN figures CYVORA already reads.

The number is the provider's liquidity figure. Phase 2 did not prove the unit
is USD, so the bands below are CYVORA policy applied to that number. Price
impact is not computed: the quote route is refused, and reserve units were
not verified. A burn status does not mean the liquidity is locked.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from integrations.gmgn.models import TokenInfo, TokenPool, TokenSecurity
from intelligence.numbers import score, show


@dataclass(frozen=True, slots=True)
class LiquidityAssessment:
    """One liquidity result."""

    status: str
    score: Decimal | None
    figure: Decimal | None
    sources: tuple[str, ...]
    burn_claim: str
    price_impact: str
    evidence: tuple[tuple[str, str], ...]
    missing: tuple[str, ...]
    warnings: tuple[str, ...]


def assess_liquidity(
    *,
    info: TokenInfo | None,
    pool: TokenPool | None,
    security: TokenSecurity | None,
    discovered_liquidity: Decimal | None,
    prior_figure: Decimal | None,
) -> LiquidityAssessment:
    """Score the lowest retrieved liquidity figure and record disagreements."""

    figures: list[tuple[str, Decimal]] = []
    if pool is not None and pool.liquidity is not None:
        figures.append(("pool_info.liquidity", pool.liquidity))
    if info is not None and info.liquidity is not None:
        figures.append(("token_info.liquidity", info.liquidity))
    if info is not None and info.pool is not None and info.pool.liquidity is not None:
        figures.append(("token_info.pool.liquidity", info.pool.liquidity))
    if discovered_liquidity is not None:
        figures.append(("discovery.liquidity", discovered_liquidity))

    warnings = [
        "Price impact was not computed. The GMGN quote route is refused, "
        "and reserve units are unverified.",
    ]
    evidence: list[tuple[str, str]] = [(name, show(value)) for name, value in figures]
    if pool is not None:
        if pool.base_reserve is not None:
            evidence.append(("base_reserve", show(pool.base_reserve)))
        if pool.quote_reserve is not None:
            evidence.append(("quote_reserve", show(pool.quote_reserve)))
    burn_claim = "unknown"
    if security is None or security.burn_status is None:
        warnings.append("No burn status is available. Liquidity is not treated as locked.")
        burn_claim = "unknown" if security is None else "not_reported"
    else:
        burn_claim = "reported"
        evidence.append(("burn_status", security.burn_status))
        warnings.append("A reported burn status is not treated as verified locked liquidity.")

    if not figures:
        return LiquidityAssessment(
            status="unknown",
            score=None,
            figure=None,
            sources=(),
            burn_claim=burn_claim,
            price_impact="not_computed",
            evidence=tuple(evidence),
            missing=("liquidity",),
            warnings=tuple(warnings),
        )

    chosen = min(value for _name, value in figures)
    points = _band(chosen)
    status = "observed"
    values = [value for _name, value in figures]
    largest = max(values)
    if largest > 0 and (largest - chosen) / largest > Decimal("0.25"):
        status = "conflicting"
        points -= Decimal(10)
        warnings.append(
            "Liquidity figures from this cycle differ by more than 25%. The lowest is used."
        )
    if prior_figure is not None and prior_figure > 0:
        change = (chosen - prior_figure) / prior_figure
        evidence.append(("prior_liquidity_change", show(change)))
        if change >= Decimal("0.10"):
            points += Decimal(5)
            warnings.append(
                "The liquidity figure is at least 10% above the previous stored snapshot."
            )
        elif change <= Decimal("-0.10"):
            points -= Decimal(10)
            warnings.append(
                "The liquidity figure is at least 10% below the previous stored snapshot."
            )
    return LiquidityAssessment(
        status=status,
        score=score(points),
        figure=chosen,
        sources=tuple(name for name, _value in figures),
        burn_claim=burn_claim,
        price_impact="not_computed",
        evidence=tuple(evidence),
        missing=(),
        warnings=tuple(warnings),
    )


def _band(figure: Decimal) -> Decimal:
    if figure < 0:
        return Decimal(0)
    if figure < 1000:
        return Decimal(15)
    if figure < 5000:
        return Decimal(35)
    if figure < 20000:
        return Decimal(55)
    if figure < 100000:
        return Decimal(75)
    return Decimal(90)
