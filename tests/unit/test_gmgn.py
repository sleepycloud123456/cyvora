"""Mocked GMGN reads. These tests do not open a socket."""

from __future__ import annotations

from decimal import Decimal

import httpx2
import pytest

from integrations.gmgn.client import GMGNClient
from integrations.gmgn.constants import ALLOWED_ROUTES, FORBIDDEN_ROUTES
from integrations.gmgn.errors import (
    GMGNAuthorizationRequired,
    GMGNError,
    GMGNExecutionBlocked,
    GMGNPlanError,
    GMGNRateLimitError,
    GMGNValidationError,
)
from integrations.gmgn.execution import GMGNExecutionGateway
from integrations.gmgn.rate_limit import GMGNRateLimiter
from integrations.gmgn.read_only import GMGNReadOnly
from integrations.gmgn.report import describe, public_scalar

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
WALLET = "11111111111111111111111111111111111111111111"


def _clock_pair() -> tuple[list[float], object, object]:
    now = [1_700_000_000.0]

    def clock() -> float:
        return now[0]

    async def sleeper(seconds: float) -> None:
        now[0] += seconds

    return now, clock, sleeper


def _client(handler: object, **kwargs: object) -> GMGNClient:
    _now, clock, sleeper = _clock_pair()
    return GMGNClient(
        "gmgn-test-key-not-real",
        transport=httpx2.MockTransport(handler),  # type: ignore[arg-type]
        clock=clock,  # type: ignore[arg-type]
        sleeper=sleeper,  # type: ignore[arg-type]
        client_id_factory=lambda: "client-id-test",
        **kwargs,  # type: ignore[arg-type]
    )


def test_allowlist_does_not_include_trade_routes() -> None:
    allowed_paths = {path for _method, path in ALLOWED_ROUTES}
    assert allowed_paths.isdisjoint(FORBIDDEN_ROUTES)
    assert all(not path.startswith("/v1/trade/") for path in allowed_paths)
    assert "/v1/user/wallet_holdings" not in allowed_paths


def test_execution_gateway_rejects_without_a_client() -> None:
    with pytest.raises(GMGNExecutionBlocked, match="Live execution is disabled"):
        GMGNExecutionGateway().submit("swap", input_amount="1")


def test_shape_report_omits_string_values() -> None:
    secret = "gmgn-test-key-not-real"
    described = describe({"api_key": secret, "rank": [{"symbol": "USDC", "price": "1"}]})
    text = str(described)
    assert secret not in text
    assert "USDC" not in text
    assert public_scalar("symbol", "USDC", allow=frozenset({"symbol"}), secret=secret) == "USDC"
    assert public_scalar("address", USDC, allow=frozenset({"address"}), secret=secret) is None


@pytest.mark.asyncio
async def test_trending_reads_the_documented_rank_route() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["header"] = request.headers["x-apikey"]
        return httpx2.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "rank": [
                        {
                            "address": USDC,
                            "symbol": "USDC",
                            "chain": "sol",
                            "price": "0.999",
                            "liquidity": "1000.50",
                            "unexpected_field": "kept",
                        }
                    ]
                },
            },
        )

    async with _client(handler) as client:
        result = await GMGNReadOnly(client).market.trending("sol", "1h", limit=3)

    url = str(seen["url"])
    assert url.startswith("https://openapi.gmgn.ai/v1/market/rank?")
    assert "timestamp=1700000000" in url
    assert "client_id=client-id-test" in url
    assert "gmgn-test-key-not-real" not in url
    assert seen["header"] == "gmgn-test-key-not-real"
    assert result.payload[0].symbol == "USDC"
    assert result.payload[0].price == Decimal("0.999")
    assert result.payload[0].model_extra is not None
    assert result.payload[0].model_extra["unexpected_field"] == "kept"
    assert result.route == "GET /v1/market/rank"


@pytest.mark.asyncio
async def test_trending_unwraps_the_nested_rank_envelope() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "code": 0,
                    "message": "success",
                    "reason": "",
                    "data": {"rank": [{"address": USDC, "symbol": "USDC", "price": 1.25}]},
                },
            },
        )

    async with _client(handler) as client:
        result = await GMGNReadOnly(client).market.trending("sol", "1h", limit=1)

    assert result.payload[0].symbol == "USDC"
    assert result.payload[0].price == Decimal("1.25")


@pytest.mark.asyncio
async def test_token_security_and_candles_parse_documented_fields() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/v1/token/security":
            return httpx2.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "renounced_mint": True,
                        "renounced_freeze_account": False,
                        "is_honeypot": "",
                        "open_source": 0,
                        "buy_tax": "0",
                        "sniper_count": 4,
                    },
                },
            )
        return httpx2.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "list": [
                        {
                            "time": 1700000000,
                            "open": "1",
                            "close": "1.1",
                            "high": "1.2",
                            "low": "0.9",
                            "volume": "10",
                            "amount": "11",
                        }
                    ]
                },
            },
        )

    async with _client(handler) as client:
        api = GMGNReadOnly(client)
        security = await api.tokens.security("sol", USDC)
        candles = await api.market.candles("sol", USDC, "1h")

    assert security.payload.open_source == 0
    assert security.payload.renounced_mint is True
    assert security.payload.renounced_freeze_account is False
    assert security.payload.sniper_count == 4
    assert candles.payload[0].volume == Decimal("10")
    assert candles.payload[0].amount == Decimal("11")


@pytest.mark.asyncio
async def test_kline_converts_unix_seconds_to_milliseconds() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        return httpx2.Response(200, json={"code": 0, "data": {"list": []}})

    async with _client(handler) as client:
        result = await GMGNReadOnly(client).market.candles(
            "sol",
            USDC,
            "1h",
            from_unix=1_700_000_000,
            to_unix=1_700_003_600,
        )

    assert "from=1700000000000" in seen["url"]
    assert "to=1700003600000" in seen["url"]
    assert result.payload == []


@pytest.mark.asyncio
async def test_trade_route_never_reaches_the_transport() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("transport was called")

    async with _client(handler) as client:
        with pytest.raises(GMGNExecutionBlocked):
            await client.get_data("POST", "/v1/trade/swap", {}, {"input_amount": "1"})
        with pytest.raises(GMGNAuthorizationRequired):
            await GMGNReadOnly(client).wallet.holdings("sol", WALLET)


@pytest.mark.asyncio
async def test_rate_limit_does_not_retry_a_long_ban() -> None:
    calls = {"count": 0}

    def handler(_request: httpx2.Request) -> httpx2.Response:
        calls["count"] += 1
        return httpx2.Response(
            429,
            json={
                "code": 429,
                "error": "RATE_LIMIT_BANNED",
                "message": "gmgn-test-key-not-real",
                "reset_at": 1_700_000_100,
            },
            headers={"x-ratelimit-reset": "1700000100"},
        )

    async with _client(handler) as client:
        with pytest.raises(GMGNRateLimitError, match="unix 1700000100") as caught:
            await client.get_data(
                "GET", "/v1/market/rank", {"chain": "sol", "interval": "1h", "limit": 1}
            )

    assert calls["count"] == 1
    assert "gmgn-test-key-not-real" not in str(caught.value)


@pytest.mark.asyncio
async def test_plan_upgrade_is_not_retried() -> None:
    calls = {"count": 0}

    def handler(_request: httpx2.Request) -> httpx2.Response:
        calls["count"] += 1
        return httpx2.Response(
            403,
            json={"code": 403, "error": "PLAN_UPGRADE_REQUIRED", "upgrade_message": "upgrade"},
        )

    async with _client(handler) as client:
        with pytest.raises(GMGNPlanError):
            await client.get_data(
                "GET",
                "/v1/market/token_kline",
                {"chain": "sol", "address": USDC, "resolution": "1s"},
            )
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_bound_account_preserves_unknown_fields() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={"code": 0, "data": {"wallets": [{"address": WALLET}], "native": "1"}},
        )

    async with _client(handler) as client:
        result = await GMGNReadOnly(client).wallet.bound_account()
    assert sorted(result.payload) == ["native", "wallets"]
    described = str(describe(result.payload))
    assert WALLET not in described


@pytest.mark.asyncio
async def test_rate_limiter_finishes_on_a_large_virtual_clock() -> None:
    now = [1_700_000_000.0]

    def clock() -> float:
        return now[0]

    async def sleeper(seconds: float) -> None:
        now[0] += seconds

    limiter = GMGNRateLimiter("free", clock=clock, sleeper=sleeper)
    for weight in (3, 2, 1, 1, 1, 2):
        await limiter.acquire(weight)


@pytest.mark.asyncio
async def test_rate_limiter_stops_when_the_clock_does_not_advance() -> None:
    async def sleeper(_seconds: float) -> None:
        return None

    limiter = GMGNRateLimiter("free", clock=lambda: 1_700_000_000.0, sleeper=sleeper)
    await limiter.acquire(5)
    with pytest.raises(GMGNError, match="clock did not advance"):
        await limiter.acquire(1)


def test_invalid_chain_and_address_are_rejected() -> None:
    with pytest.raises(GMGNValidationError):
        from integrations.gmgn.validation import require_address, require_chain

        require_chain("bitcoin")
    with pytest.raises(GMGNValidationError):
        from integrations.gmgn.validation import require_address

        require_address("not-an-address", "sol")
