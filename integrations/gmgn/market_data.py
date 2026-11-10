"""Market reads: trending lists and candlesticks."""

from __future__ import annotations

from datetime import UTC, datetime

from integrations.gmgn.auth import QueryValue
from integrations.gmgn.client import GMGNClient
from integrations.gmgn.errors import GMGNResponseError, GMGNValidationError
from integrations.gmgn.models import Candle, Retrieved, TrendingToken, object_list, parse_rows
from integrations.gmgn.validation import (
    require_address,
    require_chain,
    require_direction,
    require_interval,
    require_limit,
    require_resolution,
    require_trending_order,
)

_RANK = "GET /v1/market/rank"
_KLINE = "GET /v1/market/token_kline"


class GMGNMarketData:
    """Price and trending reads. Omitting rank filters uses GMGN's chain defaults."""

    def __init__(self, client: GMGNClient) -> None:
        self._client = client

    async def trending(
        self,
        chain: str = "sol",
        interval: str = "1h",
        *,
        limit: int = 20,
        order_by: str | None = None,
        direction: str | None = None,
    ) -> Retrieved[list[TrendingToken]]:
        """Return ``GET /v1/market/rank``.

        The official skill page says an omitted filter is not "no filter".
        Solana defaults are ``renounced`` and ``frozen``. This method does not
        send a filter, so those defaults apply.
        """

        require_chain(chain)
        require_interval(interval)
        require_limit(limit, maximum=100)
        query: dict[str, QueryValue] = {"chain": chain, "interval": interval, "limit": limit}
        if order_by is not None:
            query["order_by"] = require_trending_order(order_by)
        if direction is not None:
            query["direction"] = require_direction(direction)
        data = await self._client.get_data("GET", "/v1/market/rank", query)
        rows = object_list(_unwrap_rank(data), "rank")
        if rows is None:
            raise GMGNResponseError(_RANK, "data.rank is not a list")
        return Retrieved(_RANK, datetime.now(UTC), parse_rows(TrendingToken, rows, _RANK))

    async def candles(
        self,
        chain: str,
        address: str,
        resolution: str,
        *,
        from_unix: int | None = None,
        to_unix: int | None = None,
    ) -> Retrieved[list[Candle]]:
        """Return ``GET /v1/market/token_kline``.

        ``from_unix`` and ``to_unix`` are Unix seconds, matching the CLI flags.
        The official CLI multiplies them by 1000 before the request. The skill
        page's field table says ``volume`` is base-token size and ``amount`` is
        USD. An earlier note on that same page says the opposite, so this client
        keeps both fields and does not pick a meaning. Resolution ``1s`` is
        documented as Pro only and is still sent when asked; a free plan
        responds with ``PLAN_UPGRADE_REQUIRED``.
        """

        require_chain(chain)
        require_address(address, chain)
        require_resolution(resolution)
        query: dict[str, QueryValue] = {
            "chain": chain,
            "address": address,
            "resolution": resolution,
        }
        if from_unix is not None:
            query["from"] = _kline_millis(from_unix)
        if to_unix is not None:
            query["to"] = _kline_millis(to_unix)
        data = await self._client.get_data("GET", "/v1/market/token_kline", query)
        rows = object_list(data, "list")
        if rows is None:
            raise GMGNResponseError(_KLINE, "data.list is not a list")
        return Retrieved(_KLINE, datetime.now(UTC), parse_rows(Candle, rows, _KLINE))


def _kline_millis(seconds: int) -> int:
    if seconds < 0 or seconds >= 10**12:
        raise GMGNValidationError("Kline time must be a Unix timestamp in seconds.")
    return seconds * 1000


def _unwrap_rank(data: object) -> object:
    """Return the object that contains ``rank``.

    A live read on 2026-11-11 returned a second envelope inside ``data``:
    ``code``, ``message``, ``reason``, and ``data.rank``. Token reads do not
    do this, so the extra unwrap stays on this route.
    """

    if not isinstance(data, dict):
        return data
    code = data.get("code")
    inner = data.get("data")
    if code == 0 and not isinstance(code, bool) and isinstance(inner, dict):
        return inner
    return data
