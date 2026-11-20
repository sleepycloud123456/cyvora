"""Fresh pool quotes for open paper positions.

The radar cycle already reads pools for the tokens it analyses. This module
reads a pool only for an open position that cycle did not price, and it stops
at a small cap. It uses the existing GMGN client and rate limiter. It does
not call a trade route.
"""

from __future__ import annotations

import logging
from datetime import datetime

from config.settings import Settings
from domain.paper_trader import PoolQuote
from integrations.gmgn.client import client_from_settings
from integrations.gmgn.errors import GMGNError, GMGNRateLimitError
from integrations.gmgn.read_only import GMGNReadOnly
from trading.instruments import require_mint

logger = logging.getLogger("cyvora.paper_trader")


async def refresh_pools(
    settings: Settings,
    mints: tuple[str, ...],
    *,
    limit: int,
    now: datetime,
) -> dict[str, PoolQuote]:
    """Read up to ``limit`` pool snapshots. A missing reserve is not zero."""

    if limit < 1 or not mints or settings.gmgn_api_key is None:
        return {}
    client = client_from_settings(settings)
    surface = GMGNReadOnly(client)
    found: dict[str, PoolQuote] = {}
    try:
        for mint in mints[:limit]:
            try:
                require_mint(mint)
                retrieved = await surface.tokens.pool(settings.radar_chain, mint)
            except GMGNRateLimitError:
                logger.warning("paper pool quote stopped error_type=GMGNRateLimitError")
                break
            except GMGNError as exc:
                logger.warning("paper pool quote failed error_type=%s", type(exc).__name__)
                continue
            except Exception as exc:
                logger.warning("paper pool quote failed error_type=%s", type(exc).__name__)
                continue
            pool = retrieved.payload
            found[mint] = PoolQuote(
                mint=mint,
                price=pool.price,
                base_reserve=pool.base_reserve,
                quote_reserve=pool.quote_reserve,
                observed_at=now,
            )
    finally:
        await client.aclose()
    return found


def quote_usable(quote: PoolQuote, now: datetime, max_age: int) -> bool:
    """A mark needs recent reserves. A missing reserve is not a price."""

    if quote.observed_at.tzinfo is None or now.tzinfo is None:
        return False
    if (now - quote.observed_at).total_seconds() > max_age:
        return False
    if quote.base_reserve is None or quote.quote_reserve is None:
        return False
    return quote.base_reserve > 0 and quote.quote_reserve > 0


def stored_mark_max_age_seconds(max_quote_age: int, writeoff_seconds: int) -> int:
    """Keep last radar pool data long enough to cover GMGN rate-limit gaps."""

    return max(max_quote_age * 5, min(max(writeoff_seconds // 2, max_quote_age), 900))


def collect_marks(
    mints: tuple[str, ...],
    *,
    now: datetime,
    max_age_seconds: int,
    seeded: dict[str, PoolQuote],
    refreshed: dict[str, PoolQuote],
    stored: dict[str, PoolQuote],
    stored_max_age_seconds: int | None = None,
) -> dict[str, PoolQuote]:
    """Resolve marks for the given mints.

    Preference is a live pool refresh, then a fresh seeded (current-cycle)
    quote, then the last stored radar analysis with a longer age window.
    That last source is what an entry used when the live call is refused.
    """

    held_age = (
        stored_max_age_seconds if stored_max_age_seconds is not None else max_age_seconds
    )
    found: dict[str, PoolQuote] = {}
    for mint in mints:
        live = refreshed.get(mint)
        if live is not None and quote_usable(live, now, max_age_seconds):
            found[mint] = live
            continue
        seed = seeded.get(mint)
        if seed is not None and quote_usable(seed, now, max_age_seconds):
            found[mint] = seed
            continue
        held = stored.get(mint)
        if held is not None and quote_usable(held, now, held_age):
            found[mint] = held
    return found

