"""Read-only GMGN kline collection. The private key is not loaded."""

from __future__ import annotations

import asyncio

from config.settings import Settings
from domain.exceptions import TradingValidationError
from integrations.gmgn.client import client_from_settings
from integrations.gmgn.errors import GMGNNotConfigured
from integrations.gmgn.market_data import GMGNMarketData
from integrations.gmgn.models import Candle


def fetch_gmgn_candles(
    settings: Settings,
    mint: str,
    resolution: str,
    *,
    from_unix: int | None,
    to_unix: int | None,
) -> list[Candle]:
    """Call the documented kline read. No swap, wallet, or private key is used."""

    if settings.gmgn_api_key is None:
        raise TradingValidationError("GMGN is not configured. No market request was sent.")

    async def load() -> list[Candle]:
        client = client_from_settings(settings)
        try:
            retrieved = await GMGNMarketData(client).candles(
                "sol",
                mint,
                resolution,
                from_unix=from_unix,
                to_unix=to_unix,
            )
            return list(retrieved.payload)
        finally:
            await client.aclose()

    try:
        return asyncio.run(load())
    except GMGNNotConfigured as exc:
        raise TradingValidationError("GMGN is not configured. No market request was sent.") from exc
    except TradingValidationError:
        raise
    except Exception as exc:
        raise TradingValidationError(
            f"The GMGN kline read failed ({type(exc).__name__}). No order was sent."
        ) from None
