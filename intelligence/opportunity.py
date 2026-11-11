"""Deterministic opportunity score and rank.

Weights are fixed and documented in ``docs/intelligence/SCORING.md``. A missing
component is left out of the average. It is not treated as zero and it is not
treated as safe. Security rejection and missing critical data cap the total.
The result never authorizes an entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from domain.radar import LifecycleOutcome, SecurityCategory
from integrations.gmgn.models import Candle, TokenInfo, TokenParticipant, TokenPool, TokenSecurity
from intelligence.indicators import (
    acceleration_points,
    breakout_strength,
    momentum_points,
    volume_acceleration,
)
from intelligence.liquidity import LiquidityAssessment, assess_liquidity
from intelligence.market_regime import MarketBreadth, breadth_from_changes
from intelligence.numbers import score
from intelligence.smart_money import SmartMoneyObservation, observe_smart_money, rank_smart_count
from intelligence.token_security import SecurityAssessment, assess_security
from intelligence.whale_tracker import WhaleObservation, observe_whales

WEIGHTS: dict[str, Decimal] = {
    "security": Decimal(22),
    "liquidity": Decimal(16),
    "momentum": Decimal(14),
    "volume": Decimal(12),
    "smart_money": Decimal(12),
    "breakout": Decimal(8),
    "holder_distribution": Decimal(6),
    "market": Decimal(5),
    "feasibility": Decimal(5),
}

_GROUP = {
    "APPROVED_FOR_FURTHER_ANALYSIS": 0,
    "CAUTION": 1,
    "HIGH_RISK": 2,
    "UNKNOWN": 3,
    "REJECTED": 4,
}
_SELL_NOT_SIMULATED = "Sell feasibility was not simulated. Quote and swap routes stay refused."


@dataclass(frozen=True, slots=True)
class CandlePoint:
    """One candle kept for storage and indicators."""

    time: int | None
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: Decimal | None
    amount: Decimal | None


@dataclass(frozen=True, slots=True)
class ComponentScore:
    """One weighted piece of the total."""

    name: str
    score: Decimal | None
    weight: Decimal
    quality: str
    detail: str


@dataclass(frozen=True, slots=True)
class TokenScore:
    """The full breakdown for one token in one cycle."""

    total: Decimal | None
    decision: str
    entry_consideration: str
    research_confidence: Decimal
    components: tuple[ComponentScore, ...]
    security: SecurityAssessment
    liquidity: LiquidityAssessment
    smart_money: SmartMoneyObservation
    whales: WhaleObservation
    market: MarketBreadth
    indicators: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]
    confirmation_bonus: Decimal
    lifecycle: str


@dataclass(frozen=True, slots=True)
class ScoreInputs:
    """Retrieved reads for one token. ``None`` means that read did not happen."""

    security: TokenSecurity | None
    info: TokenInfo | None
    pool: TokenPool | None
    candles: tuple[CandlePoint, ...]
    holders: tuple[TokenParticipant, ...] | None
    traders: tuple[TokenParticipant, ...] | None
    rank_changes: tuple[Decimal, ...]
    rank_extra: dict[str, object] | None
    stale_candles: bool
    discovered_liquidity: Decimal | None
    prior_liquidity: Decimal | None
    sources: tuple[str, ...]


def score_token(inputs: ScoreInputs) -> TokenScore:
    """Score one token from the reads in ``inputs``."""

    security = assess_security(inputs.security, inputs.info)
    liquidity = assess_liquidity(
        info=inputs.info,
        pool=inputs.pool,
        security=inputs.security,
        discovered_liquidity=inputs.discovered_liquidity,
        prior_figure=inputs.prior_liquidity,
    )
    closes = tuple(point.close for point in inputs.candles if point.close is not None)
    highs = tuple(point.high for point in inputs.candles if point.high is not None)
    volumes = tuple(point.volume for point in inputs.candles if point.volume is not None)
    amounts = tuple(point.amount for point in inputs.candles if point.amount is not None)
    momentum, momentum_quality, momentum_warnings, momentum_rows = momentum_points(
        closes,
        stale=inputs.stale_candles,
    )
    volume_component, volume_rows = _volume_component(volumes, amounts, stale=inputs.stale_candles)
    breakout_component, structure = _breakout_component(
        highs,
        closes,
        volumes,
        amounts,
        stale=inputs.stale_candles,
    )
    smart = observe_smart_money(
        inputs.info,
        rank_smart_count=rank_smart_count(inputs.rank_extra),
        traders=inputs.traders,
    )
    whales = observe_whales(info=inputs.info, security=inputs.security, holders=inputs.holders)
    market = breadth_from_changes(inputs.rank_changes)
    feasibility = _feasibility(security.category, liquidity.status, inputs.traders)
    components = (
        _component(
            "security",
            security.score,
            "complete" if security.score is not None else "missing",
            security.category,
        ),
        _component("liquidity", liquidity.score, liquidity.status, liquidity.status),
        _component("momentum", momentum, momentum_quality, _detail(momentum_rows)),
        volume_component,
        _component("smart_money", smart.score, smart.status, smart.source),
        breakout_component,
        _component("holder_distribution", whales.score, whales.status, whales.source),
        _component("market", market.score, market.status, f"sample={market.sample_size}"),
        feasibility,
    )
    total = _weighted(components)
    bonus = Decimal(5) if len(inputs.sources) > 1 else Decimal(0)
    if total is not None and bonus:
        total = score(total + bonus)
    decision = _decision(security.category, liquidity.status)
    total = _cap(total, decision)
    warnings = _warnings(
        security,
        liquidity,
        smart,
        whales,
        market,
        momentum_warnings,
        volume_component,
        breakout_component,
    )
    confidence = _confidence(components, decision)
    lifecycle = _lifecycle(decision, total)
    indicators = (
        *momentum_rows,
        *volume_rows,
        ("market_structure", structure),
        ("buy_sell_pressure", "missing"),
    )
    return TokenScore(
        total=total,
        decision=decision,
        entry_consideration="not_authorized",
        research_confidence=confidence,
        components=components,
        security=security,
        liquidity=liquidity,
        smart_money=smart,
        whales=whales,
        market=market,
        indicators=indicators,
        warnings=warnings,
        confirmation_bonus=bonus,
        lifecycle=lifecycle,
    )


def explain_score(symbol: str | None, result: TokenScore) -> str:
    """Plain-language breakdown. This text is not from an external model."""

    name = symbol or "This token"
    total = "unknown" if result.total is None else f"{result.total}"
    lines = [
        f"{name} is {result.decision} with opportunity score {total}.",
        "Entry is not authorized. CYVORA did not create an order.",
        f"Security is {result.security.category}. Liquidity status is {result.liquidity.status}.",
        f"Smart-money status is {result.smart_money.status}. "
        f"Whale status is {result.whales.status}.",
    ]
    if result.confirmation_bonus:
        lines.append(
            "The token appeared in more than one discovery list, "
            "so 5 points were added before the cap."
        )
    missing = [item.name for item in result.components if item.score is None]
    if missing:
        lines.append("Missing components were left out of the average: " + ", ".join(missing) + ".")
    if result.warnings:
        lines.append("Warnings: " + " ".join(result.warnings[:4]))
    return " ".join(lines)


def rank_results[T](
    rows: list[tuple[T, TokenScore, str]],
) -> list[tuple[int, T, TokenScore]]:
    """Sort by decision group, then score, then address. Rank 1 is first."""

    ordered = sorted(
        rows,
        key=lambda item: (
            _GROUP.get(item[1].decision, 9),
            -(item[1].total if item[1].total is not None else Decimal("-1")),
            item[2],
        ),
    )
    return [(index, row, result) for index, (row, result, _address) in enumerate(ordered, start=1)]


def candles_from_gmgn(rows: tuple[Candle, ...] | list[Candle]) -> tuple[CandlePoint, ...]:
    """Copy parsed candles into the score input."""

    return tuple(
        CandlePoint(
            time=row.time,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            amount=row.amount,
        )
        for row in rows
    )


def candle_is_stale(points: tuple[CandlePoint, ...], *, now_unix: int, resolution: str) -> bool:
    """Return whether the newest candle time is outside the freshness window."""

    times = [point.time for point in points if point.time is not None]
    if not times:
        return False
    latest = max(times)
    if latest > 10**12:
        latest //= 1000
    limits = {"1m": 15 * 60, "5m": 30 * 60, "15m": 60 * 60, "1h": 3 * 60 * 60}
    return now_unix - latest > limits.get(resolution, 15 * 60)


def _component(name: str, points: Decimal | None, quality: str, detail: str) -> ComponentScore:
    return ComponentScore(
        name=name,
        score=None if points is None else score(points),
        weight=WEIGHTS[name],
        quality=quality,
        detail=detail,
    )


def _detail(rows: tuple[tuple[str, str], ...]) -> str:
    if not rows:
        return "missing"
    return ", ".join(f"{name}={value}" for name, value in rows[:3])


def _volume_component(
    volumes: tuple[Decimal, ...],
    amounts: tuple[Decimal, ...],
    *,
    stale: bool,
) -> tuple[ComponentScore, tuple[tuple[str, str], ...]]:
    volume_ratio = volume_acceleration(volumes)
    amount_ratio = volume_acceleration(amounts)
    rows: list[tuple[str, str]] = [
        ("volume_acceleration", "missing" if volume_ratio is None else format(volume_ratio, "f")),
        ("amount_acceleration", "missing" if amount_ratio is None else format(amount_ratio, "f")),
    ]
    if volume_ratio is not None and amount_ratio is not None:
        disagree = (volume_ratio >= 1 and amount_ratio < 1) or (
            amount_ratio >= 1 and volume_ratio < 1
        )
        if disagree:
            component = _component(
                "volume", None, "conflicting", "volume and amount ratios disagree"
            )
            return component, tuple(rows)
        points = acceleration_points((volume_ratio + amount_ratio) / Decimal(2))
        quality = "complete"
        detail = "volume and amount agree"
    elif volume_ratio is not None:
        points = acceleration_points(volume_ratio)
        quality = "partial"
        detail = "volume field only; USD meaning is unresolved"
    elif amount_ratio is not None:
        points = acceleration_points(amount_ratio)
        quality = "partial"
        detail = "amount field only; USD meaning is unresolved"
    else:
        return _component("volume", None, "missing", "fewer than 10 volume bars"), tuple(rows)
    if stale:
        points *= Decimal("0.5")
        quality = "stale"
    return _component("volume", points, quality, detail), tuple(rows)


def _breakout_component(
    highs: tuple[Decimal, ...],
    closes: tuple[Decimal, ...],
    volumes: tuple[Decimal, ...],
    amounts: tuple[Decimal, ...],
    *,
    stale: bool,
) -> tuple[ComponentScore, str]:
    found = breakout_strength(highs, closes)
    if found is None:
        return _component("breakout", None, "missing", "fewer than 21 bars"), "insufficient_candles"
    broke, strength = found
    ratio = volume_acceleration(volumes)
    if ratio is None:
        ratio = volume_acceleration(amounts)
    if not broke:
        points = Decimal(40)
        structure = "inside_prior_range"
        detail = f"strength={strength}"
    elif ratio is not None and ratio > Decimal("1.2"):
        points = Decimal(85)
        structure = "breakout_with_volume"
        detail = f"strength={strength}"
    else:
        points = Decimal(60)
        structure = "breakout_without_volume_confirmation"
        detail = f"strength={strength}"
    quality = "complete"
    if stale:
        points *= Decimal("0.5")
        quality = "stale"
    return _component("breakout", points, quality, detail), structure


def _feasibility(
    category: str,
    liquidity_status: str,
    traders: tuple[TokenParticipant, ...] | None,
) -> ComponentScore:
    if category == "REJECTED":
        points: Decimal | None = Decimal(0)
    elif liquidity_status == "unknown":
        points = Decimal(15)
    elif category == "UNKNOWN":
        points = Decimal(25)
    elif category == "HIGH_RISK":
        points = Decimal(35)
    elif category == "CAUTION":
        points = Decimal(55)
    elif category == "APPROVED_FOR_FURTHER_ANALYSIS":
        points = Decimal(80)
    else:
        points = None
    quality = "partial"
    if traders is not None and points is not None:
        suspicious = sum(1 for row in traders if row.is_suspicious is True)
        if suspicious:
            points -= Decimal(10)
    return ComponentScore(
        name="feasibility",
        score=None if points is None else score(points),
        weight=WEIGHTS["feasibility"],
        quality=quality,
        detail=_SELL_NOT_SIMULATED,
    )


def _weighted(components: tuple[ComponentScore, ...]) -> Decimal | None:
    present = [
        item
        for item in components
        if item.score is not None and item.quality != "conflicting" and item.weight > 0
    ]
    if not present:
        return None
    weight_sum = sum((item.weight for item in present), start=Decimal(0))
    total = sum(
        (item.score * item.weight for item in present if item.score is not None), start=Decimal(0)
    )
    return (total / weight_sum).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _decision(category: str, liquidity_status: str) -> str:
    if category == SecurityCategory.REJECTED:
        return SecurityCategory.REJECTED
    if category == SecurityCategory.UNKNOWN or liquidity_status == "unknown":
        return SecurityCategory.UNKNOWN
    if category == SecurityCategory.HIGH_RISK:
        return SecurityCategory.HIGH_RISK
    return category


def _cap(total: Decimal | None, decision: str) -> Decimal | None:
    if total is None:
        return None
    caps = {"REJECTED": Decimal(25), "UNKNOWN": Decimal(55), "HIGH_RISK": Decimal(45)}
    cap = caps.get(decision)
    if cap is None:
        return total
    return min(total, cap)


def _confidence(components: tuple[ComponentScore, ...], decision: str) -> Decimal:
    known = sum(1 for item in components if item.score is not None)
    confidence = (Decimal(known) / Decimal(len(components))) * Decimal(100)
    if decision in {"REJECTED", "UNKNOWN"}:
        confidence = min(confidence, Decimal(40))
    return confidence.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _lifecycle(decision: str, total: Decimal | None) -> LifecycleOutcome:
    if decision == SecurityCategory.REJECTED:
        return LifecycleOutcome.REJECTED
    if (
        decision == SecurityCategory.APPROVED_FOR_FURTHER_ANALYSIS
        and total is not None
        and total >= 65
    ):
        return LifecycleOutcome.WATCH_SUGGESTED
    if decision == SecurityCategory.UNKNOWN:
        return LifecycleOutcome.BLOCKED_UNKNOWN
    return LifecycleOutcome.RANKED


def _warnings(
    security: SecurityAssessment,
    liquidity: LiquidityAssessment,
    smart: SmartMoneyObservation,
    whales: WhaleObservation,
    market: MarketBreadth,
    momentum_warnings: tuple[str, ...],
    volume_component: ComponentScore,
    breakout_component: ComponentScore,
) -> tuple[str, ...]:
    rows = [
        *security.warnings,
        *liquidity.warnings,
        *smart.warnings,
        *whales.warnings,
        *market.warnings,
        *momentum_warnings,
    ]
    if volume_component.quality == "conflicting":
        rows.append("Volume and amount accelerations disagree, so the volume score was left out.")
    if breakout_component.quality == "missing":
        rows.append("Breakout was not scored because the candle window is shorter than 21 bars.")
    return tuple(dict.fromkeys(rows))
