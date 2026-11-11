"""Deterministic simulation strategies. They see only bars already revealed."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from domain.exceptions import TradingValidationError
from domain.shield import ExitKind
from domain.simulation import HistoricalBar, HistoricalSignal
from domain.trading import OrderSide

_MAX_LOOKBACK = 50


@dataclass(frozen=True)
class StrategyView:
    """The past of one mint. ``bars`` includes the decision bar and nothing after it."""

    mint: str
    decided_at: datetime
    bars: tuple[HistoricalBar, ...]
    signals: tuple[HistoricalSignal, ...]
    position_quantity: Decimal


@dataclass(frozen=True)
class StrategyIntent:
    """A requested paper action. Shield still has to approve the order."""

    side: OrderSide
    exit_kind: str
    stop_fraction: Decimal | None
    signal_ref: str | None


@dataclass(frozen=True)
class MomentumStrategy:
    """Buy after a close-to-close rise. Exits are left to the paper broker."""

    lookback: int = 2
    entry_return: Decimal = Decimal("0.05")
    stop_fraction: Decimal = Decimal("0.10")
    strategy_id: str = "momentum"
    name: str = "Momentum"
    narrative: str = "momentum"

    def on_bar(self, view: StrategyView) -> StrategyIntent | None:
        if view.position_quantity > 0:
            return None
        closes = [bar.close for bar in view.bars if bar.close is not None and bar.close > 0]
        if len(closes) <= self.lookback:
            return None
        previous = closes[-1 - self.lookback]
        change = (closes[-1] - previous) / previous
        if change < self.entry_return:
            return None
        return StrategyIntent(OrderSide.BUY, ExitKind.ENTRY.value, self.stop_fraction, None)

    def with_parameters(self, parameters: Mapping[str, str]) -> MomentumStrategy:
        lookback = _lookback(parameters.get("lookback"), self.lookback)
        entry = _fraction(parameters.get("entry_return"), self.entry_return, "Entry return")
        stop = _stop(parameters.get("stop_fraction"), self.stop_fraction)
        return MomentumStrategy(lookback, entry, stop, self.strategy_id, self.name, self.narrative)

    def parameter_pairs(self) -> tuple[tuple[str, str], ...]:
        return (
            ("lookback", str(self.lookback)),
            ("entry_return", str(self.entry_return)),
            ("stop_fraction", str(self.stop_fraction)),
        )


@dataclass(frozen=True)
class BreakoutStrategy:
    """Buy when the close exceeds the prior highs. The current high is not the signal."""

    lookback: int = 3
    stop_fraction: Decimal = Decimal("0.10")
    strategy_id: str = "breakout"
    name: str = "Breakout"
    narrative: str = "breakout"

    def on_bar(self, view: StrategyView) -> StrategyIntent | None:
        if view.position_quantity > 0:
            return None
        if len(view.bars) <= self.lookback:
            return None
        close = view.bars[-1].close
        if close is None or close <= 0:
            return None
        highs: list[Decimal] = []
        for bar in view.bars[-1 - self.lookback : -1]:
            high = bar.high if bar.high is not None else bar.close
            if high is None or high <= 0:
                return None
            highs.append(high)
        if len(highs) < self.lookback or close <= max(highs):
            return None
        return StrategyIntent(OrderSide.BUY, ExitKind.ENTRY.value, self.stop_fraction, None)

    def with_parameters(self, parameters: Mapping[str, str]) -> BreakoutStrategy:
        lookback = _lookback(parameters.get("lookback"), self.lookback)
        stop = _stop(parameters.get("stop_fraction"), self.stop_fraction)
        return BreakoutStrategy(lookback, stop, self.strategy_id, self.name, self.narrative)

    def parameter_pairs(self) -> tuple[tuple[str, str], ...]:
        return (
            ("lookback", str(self.lookback)),
            ("stop_fraction", str(self.stop_fraction)),
        )


@dataclass(frozen=True)
class SignalStrategy:
    """Trade a stored signal whose timestamp is already visible. No signal is invented."""

    strategy_id: str = "signal-follow"
    name: str = "Signal follow"
    narrative: str = "signal"
    stop_fraction: Decimal = Decimal("0.10")

    def on_bar(self, view: StrategyView) -> StrategyIntent | None:
        current = [
            item
            for item in view.signals
            if item.mint == view.mint and item.observed_at == view.decided_at
        ]
        if view.position_quantity <= 0:
            entry = next((item for item in current if item.name == "entry"), None)
            if entry is None:
                return None
            return StrategyIntent(OrderSide.BUY, ExitKind.ENTRY.value, self.stop_fraction, None)
        exit_signal = next((item for item in current if item.name == "exit"), None)
        if exit_signal is None:
            return None
        return StrategyIntent(OrderSide.SELL, ExitKind.SIGNAL.value, None, exit_signal.reference)

    def with_parameters(self, parameters: Mapping[str, str]) -> SignalStrategy:
        stop = _stop(parameters.get("stop_fraction"), self.stop_fraction)
        return SignalStrategy(self.strategy_id, self.name, self.narrative, stop)

    def parameter_pairs(self) -> tuple[tuple[str, str], ...]:
        return (("stop_fraction", str(self.stop_fraction)),)


def strategy_by_name(
    name: str, parameters: Mapping[str, str] | None = None
) -> MomentumStrategy | BreakoutStrategy | SignalStrategy:
    """Build one of the three simulation strategies. Names outside that set are rejected."""

    table: dict[str, MomentumStrategy | BreakoutStrategy | SignalStrategy] = {
        "momentum": MomentumStrategy(),
        "breakout": BreakoutStrategy(),
        "signal-follow": SignalStrategy(),
    }
    strategy = table.get(name.strip())
    if strategy is None:
        raise TradingValidationError(
            "The simulation strategy must be momentum, breakout, or signal-follow."
        )
    if not parameters:
        return strategy
    return strategy.with_parameters(parameters)


def _lookback(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    if not raw.isdecimal():
        raise TradingValidationError("Lookback must be a whole number.")
    value = int(raw)
    if value < 1 or value > _MAX_LOOKBACK:
        raise TradingValidationError("Lookback must be from 1 through 50.")
    return value


def _decimal(raw: str, label: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise TradingValidationError(f"{label} must be a decimal.") from exc
    if not value.is_finite():
        raise TradingValidationError(f"{label} must be a finite decimal.")
    return value


def _fraction(raw: str | None, default: Decimal, label: str) -> Decimal:
    if raw is None:
        return default
    value = _decimal(raw, label)
    if not value.is_finite() or value <= 0 or value > Decimal(5):
        raise TradingValidationError(f"{label} must be greater than 0 and at most 5.")
    return value


def _stop(raw: str | None, default: Decimal) -> Decimal:
    if raw is None:
        return default
    value = _decimal(raw, "Stop fraction")
    if not value.is_finite() or value <= 0 or value > Decimal("0.50"):
        raise TradingValidationError("Stop fraction must be greater than 0 and at most 0.50.")
    return value
