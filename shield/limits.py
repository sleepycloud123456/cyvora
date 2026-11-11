"""Shield limits and the checks that reject contradictory settings."""

from __future__ import annotations

from decimal import Decimal

from domain.exceptions import TradingValidationError
from domain.shield import (
    PAPER_SHIELD_DECISIONS,
    ShieldLimits,
    TakeProfitLevel,
)

_DEFAULT_LEVELS = (
    TakeProfitLevel(Decimal("0.30"), Decimal("0.25")),
    TakeProfitLevel(Decimal("0.50"), Decimal("0.25")),
    TakeProfitLevel(Decimal("1.00"), Decimal("0.25")),
    TakeProfitLevel(Decimal("2.00"), Decimal("0.25")),
)


def default_limits() -> ShieldLimits:
    """Return the documented initial controls from the master spec."""

    return ShieldLimits(
        max_deployed_fraction=Decimal("0.70"),
        min_sol_reserve_fraction=Decimal("0.10"),
        risk_per_trade_fraction=Decimal("0.01"),
        daily_loss_fraction=Decimal("0.05"),
        max_drawdown_fraction=Decimal("0.15"),
        max_consecutive_losses=3,
        max_liquidity_participation=Decimal("0.02"),
        max_cluster_fraction=Decimal("0.25"),
        max_price_impact=Decimal("0.02"),
        volatility_multiplier=Decimal("2"),
        liquidity_widen_below=Decimal("0.10"),
        young_token_seconds=86_400,
        young_token_multiplier=Decimal("1.25"),
        stressed_multiplier=Decimal("1.5"),
        trail_distance_fraction=Decimal("0.10"),
        trail_activation_fraction=Decimal("0.30"),
        break_even_fraction=Decimal("0.20"),
        trail_min_interval_seconds=60,
        liquidity_removal_ratio=Decimal("0.50"),
        price_collapse_ratio=Decimal("0.70"),
        max_quote_age_seconds=120,
        max_valuation_age_seconds=120,
        time_exit_seconds=86_400,
        take_profit_levels=_DEFAULT_LEVELS,
    )


def validate_limits(limits: ShieldLimits) -> ShieldLimits:
    """Reject settings that contradict the allocation and loss rules."""

    _fraction(limits.max_deployed_fraction, "Maximum deployed capital", positive=True)
    _fraction(limits.min_sol_reserve_fraction, "SOL reserve", positive=True)
    _fraction(limits.risk_per_trade_fraction, "Risk per trade", positive=True)
    _fraction(limits.daily_loss_fraction, "Daily loss", positive=True)
    _fraction(limits.max_drawdown_fraction, "Maximum drawdown", positive=True)
    _fraction(limits.max_liquidity_participation, "Liquidity participation", positive=True)
    _fraction(limits.max_cluster_fraction, "Correlation cluster", positive=True)
    _fraction(limits.max_price_impact, "Price impact", positive=True)
    _fraction(limits.liquidity_widen_below, "Liquidity widen threshold", positive=True)
    _fraction(limits.trail_distance_fraction, "Trailing distance", positive=True)
    _fraction(limits.trail_activation_fraction, "Trailing activation", positive=True)
    _fraction(limits.break_even_fraction, "Break-even activation", positive=True)
    _fraction(limits.liquidity_removal_ratio, "Liquidity removal", positive=True)
    _fraction(limits.price_collapse_ratio, "Price collapse", positive=True)
    if limits.max_deployed_fraction + limits.min_sol_reserve_fraction > 1:
        raise TradingValidationError(
            "Deployed capital and the SOL reserve cannot together exceed equity."
        )
    if limits.risk_per_trade_fraction > limits.daily_loss_fraction:
        raise TradingValidationError("Risk per trade cannot exceed the daily loss limit.")
    if limits.daily_loss_fraction > limits.max_drawdown_fraction:
        raise TradingValidationError("The daily loss limit cannot exceed maximum drawdown.")
    if limits.risk_per_trade_fraction > limits.max_drawdown_fraction:
        raise TradingValidationError("Risk per trade cannot exceed maximum drawdown.")
    if limits.max_cluster_fraction > limits.max_deployed_fraction:
        raise TradingValidationError("A correlation cluster cannot exceed deployed capital.")
    if limits.max_consecutive_losses < 1:
        raise TradingValidationError("Consecutive-loss protection needs a limit of at least 1.")
    _at_least(limits.volatility_multiplier, Decimal(1), "Volatility multiplier")
    _at_least(limits.young_token_multiplier, Decimal(1), "Young-token multiplier")
    _at_least(limits.stressed_multiplier, Decimal(1), "Stressed-market multiplier")
    if limits.young_token_seconds < 0 or limits.trail_min_interval_seconds < 0:
        raise TradingValidationError("Time limits cannot be negative.")
    if limits.max_quote_age_seconds < 1 or limits.max_valuation_age_seconds < 1:
        raise TradingValidationError("Quote and valuation ages must be at least one second.")
    if limits.time_exit_seconds < 1:
        raise TradingValidationError("The time exit needs a positive holding time.")
    _levels(limits.take_profit_levels)
    if limits.trail_distance_fraction >= 1:
        raise TradingValidationError("Trailing distance must stay below the price.")
    return limits


def require_paper_decision(decision: str, *, simulated: bool) -> str:
    """Accept only the paper decision vocabulary. Live approval is not a member."""

    if simulated is not True:
        raise TradingValidationError("Shield cannot store an order that is not simulated.")
    if decision not in PAPER_SHIELD_DECISIONS:
        raise TradingValidationError("The shield decision is not a paper decision.")
    return decision


def limits_payload(limits: ShieldLimits) -> dict[str, object]:
    """Serialize limits with decimal strings so the database does not use floats."""

    return {
        "version": 1,
        "max_deployed_fraction": str(limits.max_deployed_fraction),
        "min_sol_reserve_fraction": str(limits.min_sol_reserve_fraction),
        "risk_per_trade_fraction": str(limits.risk_per_trade_fraction),
        "daily_loss_fraction": str(limits.daily_loss_fraction),
        "max_drawdown_fraction": str(limits.max_drawdown_fraction),
        "max_consecutive_losses": limits.max_consecutive_losses,
        "max_liquidity_participation": str(limits.max_liquidity_participation),
        "max_cluster_fraction": str(limits.max_cluster_fraction),
        "max_price_impact": str(limits.max_price_impact),
        "volatility_multiplier": str(limits.volatility_multiplier),
        "liquidity_widen_below": str(limits.liquidity_widen_below),
        "young_token_seconds": limits.young_token_seconds,
        "young_token_multiplier": str(limits.young_token_multiplier),
        "stressed_multiplier": str(limits.stressed_multiplier),
        "trail_distance_fraction": str(limits.trail_distance_fraction),
        "trail_activation_fraction": str(limits.trail_activation_fraction),
        "break_even_fraction": str(limits.break_even_fraction),
        "trail_min_interval_seconds": limits.trail_min_interval_seconds,
        "liquidity_removal_ratio": str(limits.liquidity_removal_ratio),
        "price_collapse_ratio": str(limits.price_collapse_ratio),
        "max_quote_age_seconds": limits.max_quote_age_seconds,
        "max_valuation_age_seconds": limits.max_valuation_age_seconds,
        "time_exit_seconds": limits.time_exit_seconds,
        "take_profit_levels": [
            [str(level.gain_fraction), str(level.quantity_fraction)]
            for level in limits.take_profit_levels
        ],
    }


def limits_from_payload(payload: object) -> ShieldLimits:
    """Read a stored payload and run the same validation as a new configuration."""

    if not isinstance(payload, dict):
        raise TradingValidationError("Stored Shield limits are unreadable.")
    levels_raw = payload.get("take_profit_levels")
    if not isinstance(levels_raw, list):
        raise TradingValidationError("Stored take-profit levels are unreadable.")
    levels: list[TakeProfitLevel] = []
    for item in levels_raw:
        if not isinstance(item, list) or len(item) != 2:
            raise TradingValidationError("Stored take-profit levels are unreadable.")
        levels.append(
            TakeProfitLevel(
                _decimal(item[0], "Take-profit gain"), _decimal(item[1], "Take-profit quantity")
            )
        )
    limits = ShieldLimits(
        max_deployed_fraction=_decimal(payload.get("max_deployed_fraction"), "Maximum deployed"),
        min_sol_reserve_fraction=_decimal(payload.get("min_sol_reserve_fraction"), "SOL reserve"),
        risk_per_trade_fraction=_decimal(payload.get("risk_per_trade_fraction"), "Risk per trade"),
        daily_loss_fraction=_decimal(payload.get("daily_loss_fraction"), "Daily loss"),
        max_drawdown_fraction=_decimal(payload.get("max_drawdown_fraction"), "Maximum drawdown"),
        max_consecutive_losses=_whole(payload.get("max_consecutive_losses"), "Consecutive losses"),
        max_liquidity_participation=_decimal(
            payload.get("max_liquidity_participation"), "Liquidity participation"
        ),
        max_cluster_fraction=_decimal(payload.get("max_cluster_fraction"), "Correlation cluster"),
        max_price_impact=_decimal(payload.get("max_price_impact"), "Price impact"),
        volatility_multiplier=_decimal(
            payload.get("volatility_multiplier"), "Volatility multiplier"
        ),
        liquidity_widen_below=_decimal(payload.get("liquidity_widen_below"), "Liquidity widen"),
        young_token_seconds=_whole(payload.get("young_token_seconds"), "Young-token age"),
        young_token_multiplier=_decimal(
            payload.get("young_token_multiplier"), "Young-token multiplier"
        ),
        stressed_multiplier=_decimal(payload.get("stressed_multiplier"), "Stressed multiplier"),
        trail_distance_fraction=_decimal(
            payload.get("trail_distance_fraction"), "Trailing distance"
        ),
        trail_activation_fraction=_decimal(
            payload.get("trail_activation_fraction"), "Trailing activation"
        ),
        break_even_fraction=_decimal(payload.get("break_even_fraction"), "Break-even activation"),
        trail_min_interval_seconds=_whole(
            payload.get("trail_min_interval_seconds"), "Trailing interval"
        ),
        liquidity_removal_ratio=_decimal(
            payload.get("liquidity_removal_ratio"), "Liquidity removal"
        ),
        price_collapse_ratio=_decimal(payload.get("price_collapse_ratio"), "Price collapse"),
        max_quote_age_seconds=_whole(payload.get("max_quote_age_seconds"), "Quote age"),
        max_valuation_age_seconds=_whole(payload.get("max_valuation_age_seconds"), "Valuation age"),
        time_exit_seconds=_whole(payload.get("time_exit_seconds"), "Time exit"),
        take_profit_levels=tuple(levels),
    )
    return validate_limits(limits)


def _fraction(value: Decimal, label: str, *, positive: bool) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise TradingValidationError(f"{label} must be a decimal fraction.")
    if positive and (value <= 0 or value > 1):
        raise TradingValidationError(f"{label} must be greater than 0 and at most 1.")


def _positive(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise TradingValidationError(f"{label} must be a positive decimal.")


def _at_least(value: Decimal, floor: Decimal, label: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < floor:
        raise TradingValidationError(f"{label} must be at least {floor}.")


def _levels(levels: tuple[TakeProfitLevel, ...]) -> None:
    if not levels:
        raise TradingValidationError("Take-profit settings need at least one level.")
    previous = Decimal(0)
    total = Decimal(0)
    for level in levels:
        _positive(level.gain_fraction, "Take-profit gain")
        _fraction(level.quantity_fraction, "Take-profit quantity", positive=True)
        if level.gain_fraction <= previous:
            raise TradingValidationError("Take-profit gains must increase.")
        previous = level.gain_fraction
        total += level.quantity_fraction
    if total > 1:
        raise TradingValidationError("Planned take-profit quantity cannot exceed the position.")


def _decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, str):
        raise TradingValidationError(f"Stored {label} is unreadable.")
    try:
        parsed = Decimal(value)
    except ArithmeticError as exc:
        raise TradingValidationError(f"Stored {label} is unreadable.") from exc
    if not parsed.is_finite():
        raise TradingValidationError(f"Stored {label} is unreadable.")
    return parsed


def _whole(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TradingValidationError(f"Stored {label} is unreadable.")
    return value
