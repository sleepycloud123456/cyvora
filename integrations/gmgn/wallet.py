"""Wallet reads that the official client performs with the API key alone.

``GET /v1/user/wallet_holdings`` is intentionally absent. The official client
signs that route with ``GMGN_PRIVATE_KEY``. CYVORA does not load that key.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from integrations.gmgn.auth import QueryValue
from integrations.gmgn.client import GMGNClient
from integrations.gmgn.errors import (
    GMGNAuthorizationRequired,
    GMGNResponseError,
    GMGNValidationError,
)
from integrations.gmgn.models import (
    CreatedTokens,
    Retrieved,
    WalletActivity,
    WalletProfit,
    WalletStats,
    object_list,
    parse_model,
    parse_rows,
)
from integrations.gmgn.validation import (
    require_activity_type,
    require_address,
    require_chain,
    require_created_order,
    require_direction,
    require_limit,
    require_migrate_state,
    require_profit_period,
    require_stats_period,
)

_INFO = "GET /v1/user/info"


class GMGNWalletService:
    """Portfolio monitoring that does not sign and does not submit a transaction."""

    def __init__(self, client: GMGNClient) -> None:
        self._client = client

    async def bound_account(self) -> Retrieved[dict[str, Any]]:
        """Return ``GET /v1/user/info``.

        The official command describes this as the wallets and main-currency
        balances bound to the API key. The skill page does not publish the
        field names, so the payload is returned unchanged and is not treated
        as a complete portfolio valuation.
        """

        data = await self._client.get_data("GET", "/v1/user/info", {})
        if not isinstance(data, dict):
            raise GMGNResponseError(_INFO, f"expected an object, got {type(data).__name__}")
        return Retrieved(_INFO, datetime.now(UTC), data)

    async def holdings(self, chain: str, wallet_address: str) -> None:
        """Refuse the signed holdings route before any network call."""

        require_chain(chain)
        require_address(wallet_address, chain)
        raise GMGNAuthorizationRequired(
            "GET /v1/user/wallet_holdings requires a signed GMGN_PRIVATE_KEY. "
            "CYVORA does not load or sign with that key."
        )

    async def activity(
        self,
        chain: str,
        wallet_address: str,
        *,
        token_address: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        activity_types: list[str] | None = None,
    ) -> Retrieved[WalletActivity]:
        require_chain(chain)
        require_address(wallet_address, chain)
        query: dict[str, QueryValue] = {"chain": chain, "wallet_address": wallet_address}
        if token_address is not None:
            query["token_address"] = require_address(token_address, chain)
        if limit is not None:
            query["limit"] = require_limit(limit, maximum=100)
        if cursor is not None:
            query["cursor"] = cursor
        if activity_types:
            query["type"] = [require_activity_type(item) for item in activity_types]
        data = await self._client.get_data("GET", "/v1/user/wallet_activity", query)
        route = "GET /v1/user/wallet_activity"
        return Retrieved(route, datetime.now(UTC), parse_model(WalletActivity, data, route))

    async def stats(
        self,
        chain: str,
        wallet_addresses: list[str],
        *,
        period: str = "7d",
    ) -> Retrieved[list[WalletStats]]:
        require_chain(chain)
        require_stats_period(period)
        if not wallet_addresses:
            raise GMGNValidationError("at least one wallet is required")
        wallets = [require_address(item, chain) for item in wallet_addresses]
        data = await self._client.get_data(
            "GET",
            "/v1/user/wallet_stats",
            {"chain": chain, "wallet_address": wallets, "period": period},
        )
        route = "GET /v1/user/wallet_stats"
        rows = data if isinstance(data, list) else [data]
        return Retrieved(route, datetime.now(UTC), parse_rows(WalletStats, rows, route))

    async def profits(
        self,
        chain: str,
        wallet_addresses: list[str],
        *,
        period: str = "7d",
    ) -> Retrieved[list[WalletProfit]]:
        require_chain(chain)
        require_profit_period(period)
        if not 1 <= len(wallet_addresses) <= 100:
            raise GMGNValidationError("wallet_addresses must contain 1 to 100 addresses")
        wallets = [require_address(item, chain) for item in wallet_addresses]
        data = await self._client.get_data(
            "POST",
            "/v1/user/wallet_profits",
            {},
            {"chain": chain, "period": period, "wallet_addresses": wallets},
        )
        route = "POST /v1/user/wallet_profits"
        rows = object_list(data, "list")
        if rows is None:
            raise GMGNResponseError(route, "data.list is not a list")
        return Retrieved(route, datetime.now(UTC), parse_rows(WalletProfit, rows, route))

    async def token_balance(
        self,
        chain: str,
        wallet_address: str,
        token_address: str,
    ) -> Retrieved[dict[str, Any]]:
        """Return ``GET /v1/user/wallet_token_balance``.

        The skill page names the route and not a field table, so no balance is
        invented from a missing key.
        """

        require_chain(chain)
        require_address(wallet_address, chain)
        require_address(token_address, chain)
        data = await self._client.get_data(
            "GET",
            "/v1/user/wallet_token_balance",
            {
                "chain": chain,
                "wallet_address": wallet_address,
                "token_address": token_address,
            },
        )
        route = "GET /v1/user/wallet_token_balance"
        if not isinstance(data, dict):
            raise GMGNResponseError(route, f"expected an object, got {type(data).__name__}")
        return Retrieved(route, datetime.now(UTC), data)

    async def created_tokens(
        self,
        chain: str,
        wallet_address: str,
        *,
        order_by: str | None = None,
        direction: str | None = None,
        migrate_state: str | None = None,
    ) -> Retrieved[CreatedTokens]:
        require_chain(chain)
        require_address(wallet_address, chain)
        query: dict[str, QueryValue] = {"chain": chain, "wallet_address": wallet_address}
        if order_by is not None:
            query["order_by"] = require_created_order(order_by)
        if direction is not None:
            query["direction"] = require_direction(direction)
        if migrate_state is not None:
            query["migrate_state"] = require_migrate_state(migrate_state)
        data = await self._client.get_data("GET", "/v1/user/created_tokens", query)
        route = "GET /v1/user/created_tokens"
        return Retrieved(route, datetime.now(UTC), parse_model(CreatedTokens, data, route))
