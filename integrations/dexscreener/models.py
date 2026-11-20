"""Parsed DexScreener quotes used for marks and discovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from domain.paper_trader import PoolQuote
from integrations.dexscreener.constants import SOLANA_CHAIN_ID, WSOL_MINT

_MS_THRESHOLD = 10_000_000_000


@dataclass(frozen=True, slots=True)
class DexScreenerListing:
    """A token address advertised on a DexScreener discovery route."""

    chain_id: str
    token_address: str
    source: str


@dataclass(frozen=True, slots=True)
class DexScreenerQuote:
    """The best Solana/SOL pair CYVORA could read for one mint."""

    mint: str
    symbol: str | None
    name: str | None
    price_native: Decimal
    price_usd: Decimal | None
    liquidity_usd: Decimal | None
    liquidity_base: Decimal | None
    liquidity_quote: Decimal | None
    volume_usd: Decimal | None
    market_cap: Decimal | None
    pair_address: str | None
    pair_created_at: int | None
    dex_id: str | None
    source: str


def as_decimal(value: object) -> Decimal | None:
    """Parse a JSON number or numeric string. Non-finite values stay missing."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            return None
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = Decimal(text)
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() else None
    return None


def as_unix_seconds(value: object) -> int | None:
    """Convert a DexScreener millisecond or second timestamp to Unix seconds."""

    if isinstance(value, bool) or value is None:
        return None
    stamp: int
    if isinstance(value, int):
        stamp = value
    elif isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            return None
        stamp = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        stamp = int(value.strip())
    else:
        return None
    if stamp <= 0:
        return None
    if stamp > _MS_THRESHOLD:
        stamp //= 1000
    return stamp


def is_sol_quote_pair(pair: dict[str, Any]) -> bool:
    """True when the pair is on Solana and the quote token is wrapped SOL."""

    if pair.get("chainId") != SOLANA_CHAIN_ID:
        return False
    quote = pair.get("quoteToken")
    if not isinstance(quote, dict):
        return False
    address = quote.get("address")
    if address == WSOL_MINT:
        return True
    symbol = quote.get("symbol")
    return isinstance(symbol, str) and symbol.strip().upper() in {"SOL", "WSOL"}


def token_mint(pair: dict[str, Any]) -> str | None:
    """Return the base mint when the quote side is SOL."""

    if not is_sol_quote_pair(pair):
        return None
    base = pair.get("baseToken")
    if not isinstance(base, dict):
        return None
    address = base.get("address")
    if not isinstance(address, str) or not address or address == WSOL_MINT:
        return None
    return address


def listing_from_payload(payload: object, source: str) -> DexScreenerListing | None:
    """Read a profile or boost row. Other chains are ignored."""

    if not isinstance(payload, dict):
        return None
    chain = payload.get("chainId")
    address = payload.get("tokenAddress")
    if chain != SOLANA_CHAIN_ID or not isinstance(address, str) or not address:
        return None
    if address == WSOL_MINT:
        return None
    return DexScreenerListing(chain, address, source)


def quote_from_pair(pair: dict[str, Any], source: str = "tokens") -> DexScreenerQuote | None:
    """Build a quote from one SOL-quoted pair. priceNative is required."""

    mint = token_mint(pair)
    price = as_decimal(pair.get("priceNative"))
    if mint is None or price is None or price <= 0:
        return None
    raw_liquidity = pair.get("liquidity")
    raw_volume = pair.get("volume")
    raw_base = pair.get("baseToken")
    liquidity = raw_liquidity if isinstance(raw_liquidity, dict) else {}
    volume = raw_volume if isinstance(raw_volume, dict) else {}
    base = raw_base if isinstance(raw_base, dict) else {}
    symbol = base.get("symbol") if isinstance(base.get("symbol"), str) else None
    name = base.get("name") if isinstance(base.get("name"), str) else None
    pair_address = pair.get("pairAddress")
    dex_id = pair.get("dexId")
    return DexScreenerQuote(
        mint=mint,
        symbol=None if symbol is None else symbol.strip()[:64] or None,
        name=None if name is None else name.strip()[:256] or None,
        price_native=price,
        price_usd=as_decimal(pair.get("priceUsd")),
        liquidity_usd=as_decimal(liquidity.get("usd")),
        liquidity_base=as_decimal(liquidity.get("base")),
        liquidity_quote=as_decimal(liquidity.get("quote")),
        volume_usd=as_decimal(volume.get("h24")),
        market_cap=as_decimal(pair.get("marketCap")),
        pair_address=pair_address if isinstance(pair_address, str) else None,
        pair_created_at=as_unix_seconds(pair.get("pairCreatedAt")),
        dex_id=dex_id if isinstance(dex_id, str) else None,
        source=source,
    )


def best_sol_quotes(pairs: object, source: str = "tokens") -> dict[str, DexScreenerQuote]:
    """Keep the highest-liquidity SOL pair for each mint."""

    found: dict[str, DexScreenerQuote] = {}
    if not isinstance(pairs, list):
        return found
    for item in pairs:
        if not isinstance(item, dict):
            continue
        quote = quote_from_pair(item, source)
        if quote is None:
            continue
        current = found.get(quote.mint)
        if current is None or _liquidity(quote) > _liquidity(current):
            found[quote.mint] = quote
    return found


def reserves_for(quote: DexScreenerQuote) -> tuple[Decimal, Decimal]:
    """Build reserves whose ratio equals priceNative so marks stay consistent."""

    base = quote.liquidity_base
    if base is None or base <= 0:
        base = Decimal(1)
    return base, (base * quote.price_native)


def quote_to_pool(quote: DexScreenerQuote, now: datetime) -> PoolQuote:
    """Store a DexScreener mark in the same shape as a radar pool quote."""

    base, quote_reserve = reserves_for(quote)
    return PoolQuote(
        mint=quote.mint,
        price=quote.price_native,
        base_reserve=base,
        quote_reserve=quote_reserve,
        observed_at=now,
    )


def pairs_from_search(payload: object) -> list[dict[str, Any]]:
    """Extract the pair list from a search or token payload."""

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        rows = payload.get("pairs")
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
    return []


def listings_from_payload(payload: object, source: str) -> list[DexScreenerListing]:
    """Parse a profile or boost response, which may be a list or one object."""

    rows: list[object]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        nested = payload.get("data")
        rows = nested if isinstance(nested, list) else [payload]
    else:
        return []
    found: list[DexScreenerListing] = []
    seen: set[str] = set()
    for item in rows:
        listing = listing_from_payload(item, source)
        if listing is None or listing.token_address in seen:
            continue
        seen.add(listing.token_address)
        found.append(listing)
    return found


def _liquidity(quote: DexScreenerQuote) -> Decimal:
    if quote.liquidity_usd is not None and quote.liquidity_usd > 0:
        return quote.liquidity_usd
    return Decimal(0)
