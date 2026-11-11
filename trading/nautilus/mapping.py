"""Project a Solana mint into a Nautilus currency pair when the scales fit.

NautilusTrader 1.231.0 on this wheel uses fixed precision 9. A mint, symbol,
or price that needs more than 9 decimal places stays in CYVORA ``Decimal``
records and is not rounded into a Nautilus price.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from domain.trading import SolanaInstrument
from trading.instruments import require_instrument

NAUTILUS_VERSION = "1.231.0"
NAUTILUS_PRECISION = 9
SOLANA_VENUE = "SOLANA"


@dataclass(frozen=True)
class NautilusProjection:
    """Whether 1.231.0 can hold this instrument without rounding."""

    representable: bool
    reason: str | None
    instrument_id: str | None
    price_precision: int | None
    size_precision: int | None


def project_instrument(instrument: SolanaInstrument) -> tuple[NautilusProjection, object | None]:
    """Build a ``CurrencyPair`` or explain why this mint stays outside Nautilus."""

    checked = require_instrument(instrument)
    if (
        checked.price_decimals > NAUTILUS_PRECISION
        or checked.size_decimals > NAUTILUS_PRECISION
        or checked.quote_decimals > NAUTILUS_PRECISION
    ):
        return (
            NautilusProjection(
                False,
                "nautilus_fixed_precision_9",
                None,
                None,
                None,
            ),
            None,
        )
    pair = cast(Any, _currency_pair(checked))
    return (
        NautilusProjection(
            True,
            None,
            str(pair.id),
            checked.price_decimals,
            checked.size_decimals,
        ),
        pair,
    )


def fixed_text(value: Decimal, decimals: int) -> str:
    """Format a decimal at the instrument scale for Nautilus ``from_str``."""

    return f"{value:.{decimals}f}"


def _currency_pair(instrument: SolanaInstrument) -> object:
    from nautilus_trader.model.enums import CurrencyType
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    from nautilus_trader.model.instruments import CurrencyPair
    from nautilus_trader.model.objects import Currency, Price, Quantity

    base = Currency(
        instrument.mint,
        instrument.size_decimals,
        0,
        instrument.symbol[:64],
        CurrencyType.CRYPTO,
    )
    quote = Currency(
        instrument.quote_symbol,
        instrument.quote_decimals,
        0,
        instrument.quote_symbol,
        CurrencyType.CRYPTO,
    )
    venue = Venue(SOLANA_VENUE)
    symbol = Symbol(instrument.mint)
    return CurrencyPair(
        instrument_id=InstrumentId(symbol, venue),
        raw_symbol=symbol,
        base_currency=base,
        quote_currency=quote,
        price_precision=instrument.price_decimals,
        size_precision=instrument.size_decimals,
        price_increment=Price.from_str(_increment(instrument.price_decimals)),
        size_increment=Quantity.from_str(_increment(instrument.size_decimals)),
        ts_event=1,
        ts_init=1,
        info={
            "chain": "sol",
            "mint": instrument.mint,
            "symbol": instrument.symbol,
            "quote": instrument.quote_symbol,
            "mapping": "synthetic_spot_pair",
        },
    )


def _increment(decimals: int) -> str:
    if decimals == 0:
        return "1"
    return "0." + ("0" * (decimals - 1)) + "1"
