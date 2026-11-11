"""Idempotency keys for paper orders."""

from __future__ import annotations

import re

from domain.exceptions import TradingValidationError

_KEY = re.compile(r"^[A-Za-z0-9_.:-]{8,64}$")


def require_idempotency_key(value: str) -> str:
    """Accept a caller key. A repeated key must not create a second fill."""

    key = value.strip()
    if _KEY.fullmatch(key) is None:
        raise TradingValidationError(
            "An idempotency key must be 8 to 64 characters from letters, digits, and _.:-."
        )
    return key


def client_order_id_for(key: str) -> str:
    return f"paper-{key}"
