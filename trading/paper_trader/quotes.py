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
