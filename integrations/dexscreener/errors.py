"""Errors raised by the read-only DexScreener client."""

from __future__ import annotations


class DexScreenerError(Exception):
    """A DexScreener read failed. This never means an order was sent."""


class DexScreenerTransportError(DexScreenerError):
    """The HTTP transport failed or timed out."""


class DexScreenerResponseError(DexScreenerError):
    """The response could not be parsed or was an unexpected status."""

    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


class DexScreenerRateLimitError(DexScreenerError):
    """DexScreener refused the request because of its rate limit."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
