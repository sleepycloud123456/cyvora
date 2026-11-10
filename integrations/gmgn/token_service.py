"""Token fundamentals, security, pools, holders, and traders."""

from __future__ import annotations

from datetime import UTC, datetime

from integrations.gmgn.auth import QueryValue
from integrations.gmgn.client import GMGNClient
from integrations.gmgn.errors import GMGNResponseError
from integrations.gmgn.models import (
    Retrieved,
    TokenInfo,
    TokenParticipant,
    TokenPool,
    TokenSecurity,
    object_list,
    parse_model,
    parse_rows,
)
from integrations.gmgn.validation import (
    require_address,
    require_chain,
    require_direction,
    require_holder_order,
    require_holder_tag,
    require_limit,
)


class GMGNTokenService:
    """Exist-auth token reads. Every method takes a chain and a token address."""

    def __init__(self, client: GMGNClient) -> None:
        self._client = client

    async def info(self, chain: str, address: str) -> Retrieved[TokenInfo]:
        return await self._object("GET", "/v1/token/info", chain, address, TokenInfo)

    async def security(self, chain: str, address: str) -> Retrieved[TokenSecurity]:
        return await self._object("GET", "/v1/token/security", chain, address, TokenSecurity)

    async def pool(self, chain: str, address: str) -> Retrieved[TokenPool]:
        return await self._object("GET", "/v1/token/pool_info", chain, address, TokenPool)

    async def holders(
        self,
        chain: str,
        address: str,
        *,
        limit: int = 20,
        order_by: str = "amount_percentage",
        direction: str = "desc",
        tag: str | None = None,
    ) -> Retrieved[list[TokenParticipant]]:
        return await self._participants(
            "/v1/market/token_top_holders",
            chain,
            address,
            limit=limit,
            order_by=order_by,
            direction=direction,
            tag=tag,
        )

    async def traders(
        self,
        chain: str,
        address: str,
        *,
        limit: int = 20,
        order_by: str = "amount_percentage",
        direction: str = "desc",
        tag: str | None = None,
    ) -> Retrieved[list[TokenParticipant]]:
        return await self._participants(
            "/v1/market/token_top_traders",
            chain,
            address,
            limit=limit,
            order_by=order_by,
            direction=direction,
            tag=tag,
        )

    async def _object[T: TokenInfo | TokenSecurity | TokenPool](
        self,
        method: str,
        path: str,
        chain: str,
        address: str,
        model: type[T],
    ) -> Retrieved[T]:
        require_chain(chain)
        require_address(address, chain)
        data = await self._client.get_data(method, path, {"chain": chain, "address": address})
        route = f"{method} {path}"
        return Retrieved(route, datetime.now(UTC), parse_model(model, data, route))

    async def _participants(
        self,
        path: str,
        chain: str,
        address: str,
        *,
        limit: int,
        order_by: str,
        direction: str,
        tag: str | None,
    ) -> Retrieved[list[TokenParticipant]]:
        require_chain(chain)
        require_address(address, chain)
        require_limit(limit, maximum=100)
        query: dict[str, QueryValue] = {
            "chain": chain,
            "address": address,
            "limit": limit,
            "order_by": require_holder_order(order_by),
            "direction": require_direction(direction),
        }
        if tag is not None:
            query["tag"] = require_holder_tag(tag)
        data = await self._client.get_data("GET", path, query)
        route = f"GET {path}"
        rows = object_list(data, "list")
        if rows is None:
            raise GMGNResponseError(route, "data.list is not a list")
        return Retrieved(route, datetime.now(UTC), parse_rows(TokenParticipant, rows, route))
