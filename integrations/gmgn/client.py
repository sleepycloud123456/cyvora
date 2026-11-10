"""Read-only HTTP client for the GMGN OpenAPI."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx2

from config.settings import Settings
from integrations.gmgn.auth import GMGNAuth, QueryValue
from integrations.gmgn.connection import GMGNConnectionState
from integrations.gmgn.constants import (
    ALLOWED_ROUTES,
    FORBIDDEN_ROUTES,
    OFFICIAL_BASE_URL,
    RATE_LIMIT_RETRY_BUFFER_SECONDS,
    RATE_LIMIT_RETRY_MAX_WAIT_SECONDS,
    route_weight,
)
from integrations.gmgn.curl_transport import default_gmgn_transport
from integrations.gmgn.errors import (
    GMGNApiError,
    GMGNExecutionBlocked,
    GMGNNotConfigured,
    GMGNPlanError,
    GMGNRateLimitError,
    GMGNResponseError,
    GMGNTransportError,
)
from integrations.gmgn.rate_limit import GMGNRateLimiter

logger = logging.getLogger("cyvora.gmgn")

_RATE_LIMIT_ERRORS = frozenset(
    {
        "RATE_LIMIT_EXCEEDED",
        "RATE_LIMIT_BANNED",
        "RATE_LIMIT_BANNED_MAX",
        "ERROR_RATE_LIMIT_BLOCKED",
    }
)
_RETRYABLE_RATE_LIMITS = frozenset({"RATE_LIMIT_EXCEEDED", "RATE_LIMIT_BANNED"})


class GMGNClient:
    """Call allowlisted GMGN reads.

    On Windows the default transport is the system curl, because Cloudflare
    blocks the Python TLS stack in front of this API. IPv4 is required. Redirects
    are not followed, so the API key header cannot be sent to another host.
    Ambient proxy variables are ignored for the same reason.
    """

    def __init__(
        self,
        api_key: str,
        *,
        plan: str = "free",
        timeout: float = 10.0,
        transport: httpx2.AsyncBaseTransport | None = None,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
        client_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._clock = clock or time.time
        self._sleeper = sleeper or asyncio.sleep
        self._auth = GMGNAuth(api_key, clock=self._clock, client_id_factory=client_id_factory)
        self._limiter = GMGNRateLimiter(plan, clock=self._clock, sleeper=self._sleeper)
        self.connection = GMGNConnectionState(configured=True)
        selected = transport or default_gmgn_transport()
        self._http = httpx2.AsyncClient(
            transport=selected,
            timeout=httpx2.Timeout(timeout, connect=min(5.0, timeout)),
            follow_redirects=False,
            trust_env=False,
        )

    async def __aenter__(self) -> GMGNClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_data(
        self,
        method: str,
        path: str,
        query: Mapping[str, QueryValue | None] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> object:
        """Return the ``data`` member of a successful envelope."""

        self._guard_route(method, path)
        weight = route_weight(method, path, query or {})
        attempt = 0
        while True:
            attempt += 1
            await self._limiter.acquire(weight)
            started = time.perf_counter()
            try:
                response = await self._send(method, path, query or {}, body)
            except httpx2.TransportError as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                self.connection.record_failure(
                    method,
                    path,
                    state="unreachable",
                    http_status=None,
                    api_error=None,
                    latency_ms=latency_ms,
                )
                self._log(method, path, "transport_error", None, type(exc).__name__, latency_ms)
                if attempt == 1 and isinstance(exc, (httpx2.ConnectError, httpx2.TimeoutException)):
                    await self._sleeper(0.5)
                    continue
                raise GMGNTransportError(method, path, type(exc).__name__) from None
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                data = self._read_envelope(method, path, response)
            except GMGNTransportError:
                self.connection.record_failure(
                    method,
                    path,
                    state="unreachable",
                    http_status=response.status_code,
                    api_error=None,
                    latency_ms=latency_ms,
                )
                self._log(method, path, "redirect_refused", response.status_code, None, latency_ms)
                raise
            except GMGNResponseError:
                self.connection.record_failure(
                    method,
                    path,
                    state="rejected",
                    http_status=response.status_code,
                    api_error=None,
                    latency_ms=latency_ms,
                )
                self._log(method, path, "bad_response", response.status_code, None, latency_ms)
                raise
            except GMGNRateLimitError as exc:
                self.connection.record_failure(
                    method,
                    path,
                    state="rate_limited",
                    http_status=exc.http_status,
                    api_error=exc.api_error,
                    latency_ms=latency_ms,
                )
                self._log(method, path, "rate_limited", exc.http_status, exc.api_error, latency_ms)
                wait = self._rate_limit_wait(exc) if attempt == 1 else None
                if wait is not None:
                    await self._sleeper(wait)
                    continue
                raise
            except GMGNApiError as exc:
                state = "plan_limited" if isinstance(exc, GMGNPlanError) else "rejected"
                if exc.http_status in {401, 403} and not isinstance(exc, GMGNPlanError):
                    state = "unauthorized"
                self.connection.record_failure(
                    method,
                    path,
                    state=state,
                    http_status=exc.http_status,
                    api_error=exc.api_error,
                    latency_ms=latency_ms,
                )
                self._log(method, path, state, exc.http_status, exc.api_error, latency_ms)
                raise
            self.connection.record_success(method, path, response.status_code, latency_ms)
            self._log(method, path, "ok", response.status_code, None, latency_ms)
            return data

    def _guard_route(self, method: str, path: str) -> None:
        if path in FORBIDDEN_ROUTES or path.startswith("/v1/trade/"):
            raise GMGNExecutionBlocked(
                f"Refusing {method} {path}. CYVORA does not call GMGN trade or signing routes."
            )
        if (method, path) not in ALLOWED_ROUTES:
            raise GMGNExecutionBlocked(
                f"Refusing {method} {path}. That route is not in the Phase 2 read allowlist."
            )

    async def _send(
        self,
        method: str,
        path: str,
        query: Mapping[str, QueryValue | None],
        body: Mapping[str, Any] | None,
    ) -> httpx2.Response:
        url = f"{OFFICIAL_BASE_URL}{path}"
        return await self._http.request(
            method,
            url,
            params=self._auth.query(query),
            json=dict(body) if body is not None else None,
            headers=self._auth.headers(),
        )

    def _read_envelope(self, method: str, path: str, response: httpx2.Response) -> object:
        if response.status_code in {301, 302, 303, 307, 308}:
            raise GMGNTransportError(method, path, f"HTTP {response.status_code} redirect refused")
        try:
            payload = response.json()
        except ValueError:
            raise GMGNResponseError(
                f"{method} {path}",
                f"HTTP {response.status_code} non-JSON response",
            ) from None
        if not isinstance(payload, dict):
            raise GMGNResponseError(f"{method} {path}", "envelope is not an object")
        code = payload.get("code")
        if code == 0 and not isinstance(code, bool):
            return payload.get("data")
        api_error = payload.get("error")
        error_name = api_error if isinstance(api_error, str) else None
        reset_at = _reset_at(payload, response)
        if error_name == "PLAN_UPGRADE_REQUIRED":
            error_type: type[GMGNApiError] = GMGNPlanError
        elif error_name in _RATE_LIMIT_ERRORS or response.status_code == 429:
            error_type = GMGNRateLimitError
        else:
            error_type = GMGNApiError
        raise error_type(
            method,
            path,
            http_status=response.status_code,
            api_code=code,
            api_error=error_name,
            reset_at=reset_at,
        )

    def _rate_limit_wait(self, exc: GMGNRateLimitError) -> float | None:
        if exc.api_error not in _RETRYABLE_RATE_LIMITS or exc.reset_at is None:
            return None
        wait = max(exc.reset_at - self._clock(), 0.0) + RATE_LIMIT_RETRY_BUFFER_SECONDS
        if wait <= RATE_LIMIT_RETRY_MAX_WAIT_SECONDS:
            return wait
        return None

    def _log(
        self,
        method: str,
        path: str,
        outcome: str,
        http_status: int | None,
        api_error: str | None,
        latency_ms: int,
    ) -> None:
        logger.info(
            "gmgn method=%s path=%s outcome=%s http_status=%s api_error=%s latency_ms=%s",
            method,
            path,
            outcome,
            http_status if http_status is not None else "-",
            api_error or "-",
            latency_ms,
        )


def client_from_settings(settings: Settings, **kwargs: Any) -> GMGNClient:
    """Build a client from process settings. The key is not logged."""

    if settings.gmgn_api_key is None:
        raise GMGNNotConfigured("GMGN_API_KEY is not set.")
    return GMGNClient(
        settings.gmgn_api_key.get_secret_value(),
        plan=settings.gmgn_plan,
        timeout=settings.gmgn_timeout_seconds,
        **kwargs,
    )


def _reset_at(payload: Mapping[str, Any], response: httpx2.Response) -> int | None:
    raw = payload.get("reset_at")
    if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
        return raw
    header = response.headers.get("x-ratelimit-reset")
    if header and header.strip().isdigit():
        parsed = int(header.strip())
        return parsed if parsed > 0 else None
    return None
