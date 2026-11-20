"""Read-only HTTP client for the public DexScreener API.

No API key is sent. Timeouts, retries, a small cache, and client-side
rate limits keep the public budgets (~300 requests/minute for pair and
token routes, ~60/minute for profiles and boosts). This client cannot
reach a wallet or submit a trade.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from decimal import Decimal
from typing import Any
from urllib.parse import urljoin

import httpx2

from integrations.dexscreener.constants import (
    BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    DISCOVERY_CACHE_SECONDS,
    MAX_ATTEMPTS,
    MAX_TOKEN_ADDRESSES,
    PROFILE_REQUESTS_PER_MINUTE,
    QUOTE_CACHE_SECONDS,
    SEARCH_QUERIES,
    SOLANA_CHAIN_ID,
    TOKEN_REQUESTS_PER_MINUTE,
    USER_AGENT,
    WSOL_MINT,
)
from integrations.dexscreener.errors import (
    DexScreenerRateLimitError,
    DexScreenerResponseError,
    DexScreenerTransportError,
)
from integrations.dexscreener.models import (
    DexScreenerListing,
    DexScreenerQuote,
    best_sol_quotes,
    listings_from_payload,
    pairs_from_search,
    token_mint,
)

logger = logging.getLogger("cyvora.dexscreener")

_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


class _Bucket:
    """A leaky bucket paced to a requests-per-minute budget."""

    def __init__(
        self,
        per_minute: int,
        *,
        clock: Callable[[], float],
        sleeper: Callable[[float], Awaitable[None]],
    ) -> None:
        self.rate = per_minute / 60.0
        self.capacity = 5.0 if per_minute >= 300 else 2.0
        self._tokens = self.capacity
        self._updated = clock()
        self._clock = clock
        self._sleeper = sleeper
        self._lock: asyncio.Lock | None = None

    async def acquire(self) -> None:
        while True:
            async with self._guard():
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self.rate
            await self._sleeper(max(wait, 0.05))

    def _guard(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._updated)
        self._updated = now
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)


class DexScreenerClient:
    """Call DexScreener's public market-data routes."""

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx2.AsyncBaseTransport | None = None,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
        quote_cache_seconds: float = QUOTE_CACHE_SECONDS,
        discovery_cache_seconds: float = DISCOVERY_CACHE_SECONDS,
    ) -> None:
        self._clock = clock or time.time
        self._sleeper = sleeper or asyncio.sleep
        self._quote_ttl = quote_cache_seconds
        self._discovery_ttl = discovery_cache_seconds
        self._token_bucket = _Bucket(
            TOKEN_REQUESTS_PER_MINUTE, clock=self._clock, sleeper=self._sleeper
        )
        self._profile_bucket = _Bucket(
            PROFILE_REQUESTS_PER_MINUTE, clock=self._clock, sleeper=self._sleeper
        )
        self._quote_cache: dict[str, tuple[float, DexScreenerQuote]] = {}
        self._response_cache: dict[str, tuple[float, object]] = {}
        self._http = httpx2.AsyncClient(
            transport=transport,
            timeout=httpx2.Timeout(timeout, connect=min(5.0, timeout)),
            follow_redirects=False,
            trust_env=False,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )

    async def __aenter__(self) -> DexScreenerClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def quotes(self, mints: Sequence[str]) -> dict[str, DexScreenerQuote]:
        """Price each mint from its highest-liquidity SOL pair."""

        wanted = _unique_mints(mints)
        found: dict[str, DexScreenerQuote] = {}
        missing: list[str] = []
        now = self._clock()
        for mint in wanted:
            cached = self._quote_cache.get(mint)
            if cached is not None and cached[0] > now:
                found[mint] = cached[1]
            else:
                missing.append(mint)
        for start in range(0, len(missing), MAX_TOKEN_ADDRESSES):
            chunk = missing[start : start + MAX_TOKEN_ADDRESSES]
            path = f"/tokens/v1/{SOLANA_CHAIN_ID}/{','.join(chunk)}"
            payload = await self._get(path, bucket="token", cache_seconds=0)
            parsed = best_sol_quotes(payload, "tokens")
            for mint, quote in parsed.items():
                self._quote_cache[mint] = (now + self._quote_ttl, quote)
                found[mint] = quote
        return found

    async def latest_profiles(self) -> list[DexScreenerListing]:
        payload = await self._get(
            "/token-profiles/latest/v1",
            bucket="profile",
            cache_seconds=self._discovery_ttl,
        )
        return listings_from_payload(payload, "profile")

    async def latest_boosts(self) -> list[DexScreenerListing]:
        payload = await self._get(
            "/token-boosts/latest/v1",
            bucket="profile",
            cache_seconds=self._discovery_ttl,
        )
        return listings_from_payload(payload, "boost")

    async def search(self, query: str) -> list[dict[str, Any]]:
        payload = await self._get(
            "/latest/dex/search",
            bucket="token",
            query={"q": query},
            cache_seconds=self._discovery_ttl,
        )
        return pairs_from_search(payload)

    async def discover_solana(self, limit: int) -> tuple[DexScreenerQuote, ...]:
        """Solana tokens from boosts, profiles, and search, priced on a SOL pair."""

        if limit <= 0:
            return ()
        order: list[tuple[str, str]] = []
        seen: set[str] = set()

        def add(mint: str, source: str) -> None:
            if mint in seen or mint == WSOL_MINT:
                return
            seen.add(mint)
            order.append((mint, source))

        for listing in await self._safe_listings(self.latest_boosts, "boosts"):
            add(listing.token_address, listing.source)
        for listing in await self._safe_listings(self.latest_profiles, "profiles"):
            add(listing.token_address, listing.source)
        for query in SEARCH_QUERIES:
            try:
                for pair in await self.search(query):
                    mint = token_mint(pair)
                    if mint is not None:
                        add(mint, "search")
            except Exception as exc:
                logger.warning(
                    "dexscreener search failed query=%s error_type=%s",
                    query,
                    type(exc).__name__,
                )

        hydrate_limit = min(len(order), max(limit * 3, limit), MAX_TOKEN_ADDRESSES)
        priced = await self.quotes([mint for mint, _source in order[:hydrate_limit]])
        sources = dict(order)
        ranked = sorted(
            (priced[mint] for mint, _source in order if mint in priced),
            key=lambda item: (
                item.liquidity_usd is None,
                -(item.liquidity_usd or Decimal(0)),
                item.mint,
            ),
        )
        chosen: list[DexScreenerQuote] = []
        for quote in ranked:
            source = sources.get(quote.mint, quote.source)
            chosen.append(
                DexScreenerQuote(
                    mint=quote.mint,
                    symbol=quote.symbol,
                    name=quote.name,
                    price_native=quote.price_native,
                    price_usd=quote.price_usd,
                    liquidity_usd=quote.liquidity_usd,
                    liquidity_base=quote.liquidity_base,
                    liquidity_quote=quote.liquidity_quote,
                    volume_usd=quote.volume_usd,
                    market_cap=quote.market_cap,
                    pair_address=quote.pair_address,
                    pair_created_at=quote.pair_created_at,
                    dex_id=quote.dex_id,
                    source=source,
                )
            )
            if len(chosen) >= limit:
                break
        return tuple(chosen)

    async def _safe_listings(
        self,
        reader: Callable[[], Awaitable[list[DexScreenerListing]]],
        label: str,
    ) -> list[DexScreenerListing]:
        try:
            return await reader()
        except Exception as exc:
            logger.warning("dexscreener %s failed error_type=%s", label, type(exc).__name__)
            return []

    async def _get(
        self,
        path: str,
        *,
        bucket: str,
        query: Mapping[str, str] | None = None,
        cache_seconds: float,
    ) -> object:
        cache_key = path if not query else f"{path}?{sorted(query.items())!r}"
        if cache_seconds > 0:
            cached = self._response_cache.get(cache_key)
            if cached is not None and cached[0] > self._clock():
                return cached[1]
        limiter = self._profile_bucket if bucket == "profile" else self._token_bucket
        attempt = 0
        while True:
            attempt += 1
            await limiter.acquire()
            try:
                response = await self._http.get(
                    urljoin(BASE_URL, path),
                    params=dict(query) if query else None,
                )
            except httpx2.TransportError as exc:
                if attempt < MAX_ATTEMPTS:
                    await self._sleeper(0.5 * (2 ** (attempt - 1)))
                    continue
                raise DexScreenerTransportError(type(exc).__name__) from None
            if response.status_code in _RETRYABLE_STATUS and attempt < MAX_ATTEMPTS:
                await self._sleeper(_retry_after(response, attempt))
                continue
            if response.status_code == 429:
                raise DexScreenerRateLimitError(
                    "DexScreener rate limit was reached.",
                    retry_after=_header_wait(response),
                )
            if response.status_code >= 300:
                raise DexScreenerResponseError(
                    f"DexScreener returned HTTP {response.status_code}.",
                    http_status=response.status_code,
                )
            try:
                payload = response.json()
            except ValueError:
                raise DexScreenerResponseError(
                    "DexScreener returned a non-JSON body.",
                    http_status=response.status_code,
                ) from None
            if cache_seconds > 0:
                self._response_cache[cache_key] = (self._clock() + cache_seconds, payload)
            return payload


def _unique_mints(mints: Sequence[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for mint in mints:
        text = mint.strip()
        if not text or text in seen or text == WSOL_MINT:
            continue
        seen.add(text)
        found.append(text)
    return found


def _retry_after(response: httpx2.Response, attempt: int) -> float:
    header = _header_wait(response)
    if header is not None:
        return header
    return 0.5 * (2 ** (attempt - 1))


def _header_wait(response: httpx2.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        wait = float(raw)
    except ValueError:
        return None
    if wait < 0:
        return None
    return min(wait, 30.0)
