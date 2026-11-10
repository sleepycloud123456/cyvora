"""Trending tokens, new launchpad tokens, and search."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from integrations.gmgn.client import GMGNClient
from integrations.gmgn.errors import GMGNResponseError
from integrations.gmgn.market_data import GMGNMarketData
from integrations.gmgn.models import (
    LaunchToken,
    MarketSearch,
    Retrieved,
    TrendingToken,
    object_list,
    parse_model,
    parse_rows,
)
from integrations.gmgn.validation import require_chain, require_limit, require_search_query

_TRENCHES = "POST /v1/trenches"
_SEARCH = "GET /v1/market/search"


class GMGNDiscoveryService:
    """Read-only discovery. New launches use ``POST /v1/trenches``, which is a query."""

    def __init__(self, client: GMGNClient) -> None:
        self._client = client
        self._market = GMGNMarketData(client)

    async def trending(
        self,
        chain: str = "sol",
        interval: str = "1h",
        *,
        limit: int = 20,
    ) -> Retrieved[list[TrendingToken]]:
        return await self._market.trending(chain, interval, limit=limit)

    async def new_launches(
        self, chain: str = "sol", *, limit: int = 20
    ) -> Retrieved[list[LaunchToken]]:
        """Return the ``new_creation`` section of ``POST /v1/trenches``.

        The body matches the official client when the caller asks only for
        ``new_creation`` and does not override launchpad platforms. The server
        then applies its own platform defaults.
        """

        require_chain(chain)
        require_limit(limit, maximum=80)
        body: dict[str, Any] = {
            "version": "v2",
            "new_creation": {
                "filters": ["offchain", "onchain"],
                "launchpad_platform_v2": True,
                "limit": limit,
            },
        }
        data = await self._client.get_data("POST", "/v1/trenches", {"chain": chain}, body)
        rows = object_list(data, "new_creation")
        if rows is None:
            raise GMGNResponseError(_TRENCHES, "new_creation is not a list")
        # A live call on 2026-11-11 asked for 3 rows and the server returned 60.
        # The documented limit is still sent. The returned page is capped here.
        return Retrieved(
            _TRENCHES,
            datetime.now(UTC),
            parse_rows(LaunchToken, rows[:limit], _TRENCHES),
        )

    async def search(self, query: str, *, chain: str | None = None) -> Retrieved[MarketSearch]:
        """Return ``GET /v1/market/search``.

        The skill page says the payload is an additive passthrough. Only
        ``coins`` and ``wallets``, plus the identity fields named there, are read.
        """

        params: dict[str, str] = {"q": require_search_query(query)}
        if chain is not None:
            params["chain"] = require_chain(chain)
        data = await self._client.get_data("GET", "/v1/market/search", params)
        return Retrieved(_SEARCH, datetime.now(UTC), parse_model(MarketSearch, data, _SEARCH))
