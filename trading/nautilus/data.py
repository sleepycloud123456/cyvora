"""Adapt CYVORA market contracts into Nautilus data when every field is present.

A missing bid, ask, or base size stays missing. This module does not invent a
spread and does not connect to a data vendor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from domain.exceptions import TradingValidationError
from domain.trading import MarketQuote, SolanaInstrument
from trading.instruments import fits_scale
from trading.nautilus.mapping import NAUTILUS_PRECISION, fixed_text, project_instrument

_BARS = {
    "1m": (1, "MINUTE"),
    "5m": (5, "MINUTE"),
    "15m": (15, "MINUTE"),
    "1h": (1, "HOUR"),
}


def quote_tick(instrument: SolanaInstrument, quote: MarketQuote) -> object | None:
    """Build a top-of-book tick only when both sides and both sizes are present."""

    if quote.bid is None or quote.ask is None or quote.bid_size is None or quote.ask_size is None:
        return None
    pair = _ready(instrument)
    if pair is None:
        return None
    _require_price(quote.bid, instrument.price_decimals)
    _require_price(quote.ask, instrument.price_decimals)
    _require_size(quote.bid_size, instrument.size_decimals)
    _require_size(quote.ask_size, instrument.size_decimals)
    from nautilus_trader.model.data import QuoteTick
    from nautilus_trader.model.objects import Price, Quantity

    stamp = _nanos(quote.observed_at)
    return QuoteTick(
        pair.id,
        Price.from_str(fixed_text(quote.bid, instrument.price_decimals)),
        Price.from_str(fixed_text(quote.ask, instrument.price_decimals)),
        Quantity.from_str(fixed_text(quote.bid_size, instrument.size_decimals)),
        Quantity.from_str(fixed_text(quote.ask_size, instrument.size_decimals)),
        stamp,
        stamp,
    )


def trade_tick(instrument: SolanaInstrument, quote: MarketQuote) -> object | None:
    """Build a trade tick only when the caller marked the size as base tokens."""

    if quote.last_price is None or quote.last_size is None or not quote.size_is_base:
        return None
    pair = _ready(instrument)
    if pair is None:
        return None
    _require_price(quote.last_price, instrument.price_decimals)
    _require_size(quote.last_size, instrument.size_decimals)
    from nautilus_trader.model.data import TradeTick
    from nautilus_trader.model.enums import AggressorSide
    from nautilus_trader.model.identifiers import TradeId
    from nautilus_trader.model.objects import Price, Quantity

    stamp = _nanos(quote.observed_at)
    return TradeTick(
        pair.id,
        Price.from_str(fixed_text(quote.last_price, instrument.price_decimals)),
        Quantity.from_str(fixed_text(quote.last_size, instrument.size_decimals)),
        AggressorSide.NO_AGGRESSOR,
        TradeId("cyvora-supplied"),
        stamp,
        stamp,
    )


def bar(instrument: SolanaInstrument, quote: MarketQuote) -> object | None:
    """Build an external bar when OHLC, a base size, and a known resolution exist."""

    if (
        quote.open is None
        or quote.high is None
        or quote.low is None
        or quote.close is None
        or quote.last_size is None
        or not quote.size_is_base
        or quote.bar_resolution not in _BARS
    ):
        return None
    pair = _ready(instrument)
    if pair is None:
        return None
    for price in (quote.open, quote.high, quote.low, quote.close):
        _require_price(price, instrument.price_decimals)
    _require_size(quote.last_size, instrument.size_decimals)
    step, aggregation_name = _BARS[quote.bar_resolution]
    from nautilus_trader.model.data import Bar, BarSpecification, BarType
    from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType
    from nautilus_trader.model.objects import Price, Quantity

    spec = BarSpecification(step, getattr(BarAggregation, aggregation_name), PriceType.LAST)
    bar_type = BarType(pair.id, spec, AggregationSource.EXTERNAL)
    stamp = _nanos(quote.observed_at)
    return Bar(
        bar_type,
        Price.from_str(fixed_text(quote.open, instrument.price_decimals)),
        Price.from_str(fixed_text(quote.high, instrument.price_decimals)),
        Price.from_str(fixed_text(quote.low, instrument.price_decimals)),
        Price.from_str(fixed_text(quote.close, instrument.price_decimals)),
        Quantity.from_str(fixed_text(quote.last_size, instrument.size_decimals)),
        stamp,
        stamp,
    )


def _ready(instrument: SolanaInstrument) -> Any | None:
    projection, pair = project_instrument(instrument)
    if projection.price_precision is not None and projection.price_precision > NAUTILUS_PRECISION:
        return None
    if pair is None:
        return None
    return cast(Any, pair)


def _require_price(value: Decimal, decimals: int) -> None:
    if value <= 0 or not fits_scale(value, decimals):
        raise TradingValidationError("A Nautilus price must be positive and fit the instrument.")


def _require_size(value: Decimal, decimals: int) -> None:
    if value <= 0 or not fits_scale(value, decimals):
        raise TradingValidationError("A Nautilus size must be positive and fit the instrument.")


def _nanos(value: datetime) -> int:
    moment = value.astimezone(UTC)
    origin = datetime(1970, 1, 1, tzinfo=UTC)
    delta = moment - origin
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000
