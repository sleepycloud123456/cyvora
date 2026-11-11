"""Solana instrument identity and decimal scale checks."""

from __future__ import annotations

import re
from decimal import Decimal

from domain.exceptions import TradingValidationError
from domain.trading import SolanaInstrument

_MINT = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_SYMBOL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_QUOTE = re.compile(r"^[A-Z0-9]{2,12}$")
_MAX_DECIMALS = 18


def require_mint(value: str) -> str:
    """Accept a base58 Solana mint. This does not look the account up."""

    mint = value.strip()
    if _MINT.fullmatch(mint) is None:
        raise TradingValidationError("A Solana mint must be 32 to 44 base58 characters.")
    return mint


def require_symbol(value: str) -> str:
    symbol = value.strip()
    if _SYMBOL.fullmatch(symbol) is None:
        raise TradingValidationError("A token symbol must be 1 to 32 letters, digits, or ._-.")
    return symbol


def require_quote_symbol(value: str) -> str:
    quote = value.strip().upper()
    if _QUOTE.fullmatch(quote) is None:
        raise TradingValidationError("A quote symbol must be 2 to 12 uppercase letters or digits.")
    return quote


def require_decimals(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TradingValidationError(f"{label} must be a whole number.")
    if value < 0 or value > _MAX_DECIMALS:
        raise TradingValidationError(f"{label} must be from 0 through {_MAX_DECIMALS}.")
    return value


def require_instrument(instrument: SolanaInstrument) -> SolanaInstrument:
    """Return the instrument when its identity and scales are usable."""

    return SolanaInstrument(
        mint=require_mint(instrument.mint),
        symbol=require_symbol(instrument.symbol),
        size_decimals=require_decimals(instrument.size_decimals, "Size decimals"),
        price_decimals=require_decimals(instrument.price_decimals, "Price decimals"),
        quote_symbol=require_quote_symbol(instrument.quote_symbol),
        quote_decimals=require_decimals(instrument.quote_decimals, "Quote decimals"),
    )


def fits_scale(value: Decimal, decimals: int) -> bool:
    """True when ``value`` does not need more fractional digits than ``decimals``."""

    quantum = Decimal(1).scaleb(-decimals)
    return value == value.quantize(quantum)


def require_scaled(value: Decimal, decimals: int, label: str) -> Decimal:
    if not fits_scale(value, decimals):
        raise TradingValidationError(
            f"{label} has more fractional digits than the instrument allows."
        )
    return value


def require_positive(value: Decimal, label: str) -> Decimal:
    if value <= 0:
        raise TradingValidationError(f"{label} must be positive.")
    return value


def require_non_negative(value: Decimal, label: str) -> Decimal:
    if value < 0:
        raise TradingValidationError(f"{label} cannot be negative.")
    return value
