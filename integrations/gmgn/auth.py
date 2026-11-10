"""Exist-auth headers for GMGN read calls.

The official client signs swap and holdings requests with ``GMGN_PRIVATE_KEY``.
This module does not sign anything and does not read that variable.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from uuid import uuid4

from integrations.gmgn.constants import USER_AGENT
from integrations.gmgn.errors import GMGNNotConfigured

QueryScalar = str | int | float | bool
QueryValue = QueryScalar | list[str]
QueryPair = tuple[str, str | int | float | bool | None]


class GMGNAuth:
    """Build the API-key header and the timestamp query GMGN expects."""

    def __init__(
        self,
        api_key: str,
        *,
        clock: Callable[[], float] | None = None,
        client_id_factory: Callable[[], str] | None = None,
    ) -> None:
        stripped = api_key.strip()
        if not stripped:
            raise GMGNNotConfigured("GMGN API key is empty.")
        self._api_key = stripped
        self._clock = clock or _unix_time
        self._client_id_factory = client_id_factory or (lambda: str(uuid4()))

    def __repr__(self) -> str:
        return "GMGNAuth(api_key='***')"

    def headers(self) -> dict[str, str]:
        return {
            "X-APIKEY": self._api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }

    def query(self, extra: Mapping[str, QueryValue | None]) -> list[QueryPair]:
        """Return query pairs including ``timestamp`` and ``client_id``.

        The official server accepts the timestamp for about five seconds and
        rejects a repeated ``client_id`` for about seven seconds.
        """

        pairs: list[QueryPair] = []
        for key, value in extra.items():
            if value is None:
                continue
            pairs.extend(_pairs(key, value))
        pairs.append(("timestamp", str(int(self._clock()))))
        pairs.append(("client_id", self._client_id_factory()))
        return pairs


def _unix_time() -> float:
    import time

    return time.time()


def _pairs(key: str, value: QueryValue) -> list[QueryPair]:
    if isinstance(value, bool):
        return [(key, "true" if value else "false")]
    if isinstance(value, list):
        return [(key, item) for item in value]
    return [(key, str(value))]
