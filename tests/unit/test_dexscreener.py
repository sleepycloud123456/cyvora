"""The DexScreener client is read-only market data with mocked HTTP."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx2
import pytest

from integrations.dexscreener.client import DexScreenerClient
from integrations.dexscreener.constants import BASE_URL, WSOL_MINT
from integrations.dexscreener.errors import DexScreenerRateLimitError
from integrations.dexscreener.models import quote_to_pool, reserves_for

BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
PEPE = "HeLp6NuQkmYB4pYWo2zYs22mESHXPQYzXbB8n4V98jwC"
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def _pair(
    mint: str,
    symbol: str,
    *,
    price: str = "0.00025",
    liq_usd: float = 50000.0,
    liq_base: float = 1_000_000.0,
    liq_quote: float = 250.0,
    volume: float = 20000.0,
    created_ms: int = 1_700_000_000_000,
) -> dict[str, object]:
    return {
        "chainId": "solana",
        "dexId": "raydium",
        "pairAddress": f"pair{mint[:8]}",
        "baseToken": {"address": mint, "name": symbol, "symbol": symbol},
        "quoteToken": {
            "address": WSOL_MINT,
            "name": "Wrapped SOL",
            "symbol": "SOL",
        },
        "priceNative": price,
        "priceUsd": "0.02",
        "liquidity": {"usd": liq_usd, "base": liq_base, "quote": liq_quote},
        "volume": {"h24": volume, "h6": volume, "h1": 1, "m5": 1},
        "marketCap": 80000,
        "pairCreatedAt": created_ms,
    }


def _client(
    handler: object,
    *,
    now: list[float] | None = None,
    quote_cache_seconds: float = 20.0,
) -> DexScreenerClient:
    clock_now = now or [1_700_000_000.0]

    def clock() -> float:
        return clock_now[0]

    async def sleeper(seconds: float) -> None:
        clock_now[0] += seconds

    return DexScreenerClient(
        transport=httpx2.MockTransport(handler),
        clock=clock,
        sleeper=sleeper,
        quote_cache_seconds=quote_cache_seconds,
        discovery_cache_seconds=60.0,
    )


@pytest.mark.asyncio
async def test_quotes_use_highest_liquidity_sol_pair_and_price_native() -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        assert request.headers.get("Authorization") is None
        assert str(request.url).startswith(BASE_URL)
        assert request.url.path == f"/tokens/v1/solana/{BONK}"
        weak = _pair(BONK, "BONK", price="0.0001", liq_usd=1000, liq_base=100, liq_quote=0.01)
        strong = _pair(BONK, "BONK", price="0.00025", liq_usd=80000, liq_base=400000, liq_quote=100)
        usd_quote = _pair(BONK, "BONK", price="1.5", liq_usd=999999)
        usd_quote["quoteToken"] = {
            "address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "name": "USD Coin",
            "symbol": "USDC",
        }
        return httpx2.Response(200, json=[weak, usd_quote, strong])

    async with _client(handler) as client:
        found = await client.quotes((BONK, BONK, " "))
    assert set(found) == {BONK}
    quote = found[BONK]
    assert quote.price_native == Decimal("0.00025")
    assert quote.liquidity_usd == Decimal("80000.0")
    pool = quote_to_pool(quote, NOW)
    assert pool.price == Decimal("0.00025")
    assert pool.base_reserve is not None and pool.quote_reserve is not None
    assert (pool.quote_reserve / pool.base_reserve) == quote.price_native
    assert reserves_for(quote)[1] / reserves_for(quote)[0] == quote.price_native
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_quotes_are_cached_and_batched() -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.path)
        path = request.url.path
        assert path.startswith("/tokens/v1/solana/")
        mints = path.rsplit("/", 1)[1].split(",")
        assert set(mints) == {BONK, PEPE}
        return httpx2.Response(
            200,
            json=[_pair(BONK, "BONK"), _pair(PEPE, "PEPE", price="0.001")],
        )

    async with _client(handler) as client:
        first = await client.quotes((BONK, PEPE))
        second = await client.quotes((BONK,))
    assert first[BONK].price_native == Decimal("0.00025")
    assert second[BONK] is first[BONK]
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_rate_limit_is_retried_then_raised() -> None:
    seen = {"count": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        del request
        seen["count"] += 1
        return httpx2.Response(429, headers={"Retry-After": "0.1"}, json={"error": "rate"})

    client = _client(handler)
    with pytest.raises(DexScreenerRateLimitError):
        await client.quotes((BONK,))
    await client.aclose()
    assert seen["count"] == 3


@pytest.mark.asyncio
async def test_discover_filters_solana_dedupes_and_respects_limit() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path == "/token-boosts/latest/v1":
            return httpx2.Response(
                200,
                json=[
                    {"chainId": "solana", "tokenAddress": BONK},
                    {"chainId": "bsc", "tokenAddress": "0xdead"},
                    {"chainId": "solana", "tokenAddress": BONK},
                ],
            )
        if path == "/token-profiles/latest/v1":
            return httpx2.Response(
                200,
                json=[{"chainId": "solana", "tokenAddress": PEPE}],
            )
        if path == "/latest/dex/search":
            return httpx2.Response(
                200,
                json={"schemaVersion": "1", "pairs": [_pair(BONK, "BONK"), _pair(PEPE, "PEPE")]},
            )
        if path.startswith("/tokens/v1/solana/"):
            mints = set(path.rsplit("/", 1)[1].split(","))
            rows = []
            if BONK in mints:
                rows.append(_pair(BONK, "BONK", liq_usd=20000))
            if PEPE in mints:
                rows.append(_pair(PEPE, "PEPE", price="0.001", liq_usd=90000))
            return httpx2.Response(200, json=rows)
        raise AssertionError(path)

    async with _client(handler) as client:
        found = await client.discover_solana(1)
    assert len(found) == 1
    assert found[0].mint == PEPE
    assert found[0].source == "profile"
    assert found[0].liquidity_usd == Decimal("90000.0")


def test_dexscreener_package_has_no_wallet_or_trade_path() -> None:
    root = Path(__file__).resolve().parents[2] / "integrations" / "dexscreener"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "Authorization" not in text
    assert "private_key" not in text.lower()
    assert "/v1/trade/" not in text
    assert "sign_transaction" not in text
    assert "GMGN_PRIVATE_KEY" not in text
