"""Price and volume indicators computed from stored candles.

The formulas are the ordinary published ones. A short candle list returns
``None`` instead of a filled-in value. ``volume`` and ``amount`` are never
labeled as dollars: the GMGN skill page contradicts itself on which is USD.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from intelligence.numbers import score

_ZERO = Decimal(0)
_ONE = Decimal(1)


def rsi(closes: Sequence[Decimal], period: int = 14) -> Decimal | None:
    """Wilder RSI. Flat series are undefined and return ``None``."""

    if period < 1 or len(closes) < period + 1:
        return None
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for previous, current in zip(closes, closes[1:], strict=False):
        delta = current - previous
        gains.append(delta if delta > 0 else _ZERO)
        losses.append(-delta if delta < 0 else _ZERO)
    avg_gain = sum(gains[:period], start=_ZERO) / Decimal(period)
    avg_loss = sum(losses[:period], start=_ZERO) / Decimal(period)
    for gain, loss in zip(gains[period:], losses[period:], strict=False):
        avg_gain = ((avg_gain * Decimal(period - 1)) + gain) / Decimal(period)
        avg_loss = ((avg_loss * Decimal(period - 1)) + loss) / Decimal(period)
    if avg_gain == 0 and avg_loss == 0:
        return None
    if avg_loss == 0:
        return Decimal(100)
    relative = avg_gain / avg_loss
    return Decimal(100) - (Decimal(100) / (_ONE + relative))


def macd_histogram(
    closes: Sequence[Decimal],
    *,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Decimal | None:
    """Return the last MACD histogram value, or ``None`` when the window is short."""

    if fast >= slow or signal < 1 or len(closes) < slow + signal - 1:
        return None
    fast_series = ema_series(closes, fast)
    slow_series = ema_series(closes, slow)
    if fast_series is None or slow_series is None:
        return None
    offset = len(fast_series) - len(slow_series)
    macd_line = [
        fast_series[offset + index] - slow_value for index, slow_value in enumerate(slow_series)
    ]
    signal_line = ema_series(macd_line, signal)
    if signal_line is None:
        return None
    return macd_line[-1] - signal_line[-1]


def ema_series(values: Sequence[Decimal], period: int) -> list[Decimal] | None:
    """EMA seeded with a simple average of the first ``period`` values."""

    if period < 1 or len(values) < period:
        return None
    seed = sum(values[:period], start=_ZERO) / Decimal(period)
    alpha = Decimal(2) / Decimal(period + 1)
    series = [seed]
    for value in values[period:]:
        previous = series[-1]
        series.append(((value - previous) * alpha) + previous)
    return series


def return_volatility(closes: Sequence[Decimal]) -> Decimal | None:
    """Sample standard deviation of simple close-to-close returns.

    The window is the candles CYVORA stored. It is not annualized.
    """

    if len(closes) < 6:
        return None
    returns: list[Decimal] = []
    for previous, current in zip(closes, closes[1:], strict=False):
        if previous <= 0:
            return None
        returns.append((current - previous) / previous)
    if len(returns) < 5:
        return None
    mean = sum(returns, start=_ZERO) / Decimal(len(returns))
    variance = sum((item - mean) ** 2 for item in returns) / Decimal(len(returns) - 1)
    return variance.sqrt()


def price_return(closes: Sequence[Decimal]) -> Decimal | None:
    """Return the last close divided by the first close, minus one."""

    if len(closes) < 2 or closes[0] <= 0:
        return None
    return (closes[-1] - closes[0]) / closes[0]


def volume_acceleration(values: Sequence[Decimal], window: int = 5) -> Decimal | None:
    """Recent window sum divided by the prior window sum.

    A zero prior sum is undefined. Negative prints are rejected.
    """

    if window < 1 or len(values) < window * 2:
        return None
    recent_values = values[-window:]
    prior_values = values[-2 * window : -window]
    if any(item < 0 for item in recent_values) or any(item < 0 for item in prior_values):
        return None
    prior = sum(prior_values, start=_ZERO)
    if prior == 0:
        return None
    return sum(recent_values, start=_ZERO) / prior


def breakout_strength(
    highs: Sequence[Decimal],
    closes: Sequence[Decimal],
    *,
    lookback: int = 20,
) -> tuple[bool, Decimal] | None:
    """Compare the last close with the highest high of the previous bars.

    The last bar is excluded from the prior high so the close is not compared
    with itself.
    """

    if lookback < 1 or len(closes) < lookback + 1 or len(highs) < lookback + 1:
        return None
    prior_high = max(highs[-(lookback + 1) : -1])
    last_close = closes[-1]
    if prior_high <= 0:
        return None
    strength = (last_close - prior_high) / prior_high
    return last_close > prior_high, strength


def rsi_points(value: Decimal) -> Decimal:
    """Map RSI into the momentum blend. Extended readings are not a bonus."""

    if value < 30:
        return Decimal(55)
    if value < 50:
        return Decimal(45)
    if value <= 70:
        return Decimal(70)
    if value <= 80:
        return Decimal(60)
    return Decimal(40)


def return_points(change: Decimal) -> tuple[Decimal, str | None]:
    """Map a fractional close-to-close change. Large spikes are capped."""

    if change <= Decimal("-0.2"):
        return Decimal(10), None
    if change <= 0:
        return Decimal(35), None
    if change <= Decimal("0.1"):
        return Decimal(60), None
    if change <= Decimal("0.5"):
        return Decimal(80), None
    return (
        Decimal(70),
        "The close-to-close move is above 50%. A larger spike does not raise the score.",
    )


def acceleration_points(ratio: Decimal) -> Decimal:
    """Map a unit-free recent/prior volume ratio."""

    if ratio < Decimal("0.8"):
        return Decimal(30)
    if ratio <= Decimal("1.2"):
        return Decimal(50)
    if ratio <= Decimal(2):
        return Decimal(75)
    return Decimal(85)


def momentum_points(
    closes: Sequence[Decimal],
    *,
    stale: bool,
) -> tuple[Decimal | None, str, tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Return momentum score, quality, warnings, and indicator rows."""

    change = price_return(closes)
    if change is None:
        return None, "missing", (), (("price_return", "missing"),)
    points, warning = return_points(change)
    warnings = (warning,) if warning else ()
    quality = "complete"
    rows: list[tuple[str, str]] = [("price_return", format(change, "f"))]
    rsi_value = rsi(closes)
    if rsi_value is None:
        quality = "partial"
        rows.append(("rsi_14", "missing"))
    else:
        points = (points + rsi_points(rsi_value)) / Decimal(2)
        rows.append(("rsi_14", format(rsi_value, "f")))
    histogram = macd_histogram(closes)
    if histogram is None:
        quality = "partial"
        rows.append(("macd_histogram", "missing"))
    else:
        rows.append(("macd_histogram", format(histogram, "f")))
        disagrees = (histogram > 0 and change < 0) or (histogram < 0 and change > 0)
        if disagrees:
            points -= Decimal(10)
            quality = "partial"
            warnings = (*warnings, "MACD histogram and the close-to-close return disagree.")
    volatility = return_volatility(closes)
    if volatility is None:
        rows.append(("return_volatility", "missing"))
    else:
        rows.append(("return_volatility", format(volatility, "f")))
        if volatility > Decimal("0.2"):
            points -= Decimal(5)
            quality = "partial"
            warnings = (*warnings, "Close-to-close volatility is above 0.20 in this window.")
    if stale:
        points *= Decimal("0.5")
        quality = "stale"
        warnings = (*warnings, "The newest candle is older than the freshness window.")
    return score(points), quality, warnings, tuple(rows)
