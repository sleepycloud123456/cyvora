"""Emergency classification. A trigger records a condition and does not submit an order."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from domain.shield import EmergencyEvidence, ShieldLimits

_TAG_MAX = 48


def assess_emergency(
    evidence: EmergencyEvidence | None,
    limits: ShieldLimits,
    now: datetime,
) -> tuple[str, ...]:
    """Name the triggers the evidence supports.

    A missing liquidity pair does not become a liquidity-removal event. A
    missing quote is a market-data failure. A whale or smart-money flag
    without a source is ignored.
    """

    if evidence is None or evidence.quote_observed_at is None or evidence.current_price is None:
        return ("market_data_failure",)
    age = now - evidence.quote_observed_at
    if age > timedelta(seconds=limits.max_quote_age_seconds) or age < timedelta(0):
        return ("market_data_failure",)
    triggers: list[str] = []
    if _ratio_at_most(
        evidence.current_liquidity,
        evidence.previous_liquidity,
        limits.liquidity_removal_ratio,
    ):
        triggers.append("liquidity_removal")
    if _ratio_at_most(evidence.current_price, evidence.previous_price, limits.price_collapse_ratio):
        triggers.append("price_collapse")
    if evidence.whale_sell_reported and _source(evidence.whale_source):
        triggers.append("whale_selling")
    if evidence.smart_money_exit_reported and _source(evidence.smart_money_source):
        triggers.append("smart_money_exit")
    impact = evidence.estimated_impact
    if impact is not None and impact >= limits.max_price_impact:
        triggers.append("abnormal_impact")
    if evidence.trading_restricted and _source(evidence.restriction_source):
        triggers.append("trading_restriction")
    return tuple(triggers)


def _ratio_at_most(current: Decimal | None, previous: Decimal | None, limit: Decimal) -> bool:
    if current is None or previous is None or previous <= 0 or current < 0:
        return False
    return current / previous <= limit


def _source(value: str | None) -> bool:
    if value is None:
        return False
    token = value.strip()
    return 0 < len(token) <= _TAG_MAX and token.replace("_", "").replace("-", "").isalnum()
