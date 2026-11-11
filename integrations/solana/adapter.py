"""Turn supplied Solana observations into market-data contracts.

GMGN candles use the fields already parsed by the read-only client. A candle
close becomes a last price. Bid and ask stay empty because those routes do
not provide a book. Volume is copied as volume and is not treated as a base
size. No RPC, wallet, or transaction call is made.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from domain.exceptions import TradingValidationError
from domain.trading import MarketQuote
from integrations.gmgn.models import Candle
from trading.instruments import require_mint

_RESOLUTIONS = frozenset({"1m", "5m", "15m", "1h"})


def adapt_observation(
    mint: str,
    observed_at: datetime,
    *,
    source: str,
    bid: Decimal | None = None,
    ask: Decimal | None = None,
    bid_size: Decimal | None = None,
    ask_size: Decimal | None = None,
    last_price: Decimal | None = None,
    last_size: Decimal | None = None,
    volume: Decimal | None = None,
    open_price: Decimal | None = None,
    high: Decimal | None = None,
    low: Decimal | None = None,
    close: Decimal | None = None,
    size_is_base: bool = False,
    bar_resolution: str | None = None,
) -> MarketQuote:
    """Build a contract from values the caller already has."""

    if observed_at.tzinfo is None:
        raise TradingValidationError("A market observation needs a timezone-aware time.")
    label = source.strip()
    if not label or len(label) > 64:
        raise TradingValidationError("A market source name must be 1 to 64 characters.")
    resolution = bar_resolution
    if resolution is not None and resolution not in _RESOLUTIONS:
        raise TradingValidationError("Bar resolution must be 1m, 5m, 15m, or 1h.")
    return MarketQuote(
        mint=require_mint(mint),
        observed_at=observed_at.astimezone(UTC),
        source=label,
        bid=bid,
        ask=ask,
        bid_size=bid_size,
        ask_size=ask_size,
        last_price=last_price,
        last_size=last_size,
        volume=volume,
        open=open_price,
        high=high,
        low=low,
        close=close,
        size_is_base=size_is_base,
        bar_resolution=resolution,
    )


def adapt_gmgn_candle(mint: str, candle: Candle, observed_at: datetime) -> MarketQuote:
    """Map one stored GMGN candle. Missing OHLC stays missing."""

    observed = observed_at if candle.time is None else datetime.fromtimestamp(candle.time, UTC)
    return adapt_observation(
        mint,
        observed,
        source="gmgn_candle",
        last_price=candle.close,
        volume=candle.volume,
        open_price=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        size_is_base=False,
    )
