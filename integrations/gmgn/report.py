"""Shape reports that cannot contain an API key or a wallet address."""

from __future__ import annotations

import re

from integrations.gmgn.errors import GMGNError

_ADDRESS = re.compile(r"^(?:[1-9A-HJ-NP-Za-km-z]{32,44}|0x[0-9a-fA-F]{40})$")


def describe(value: object, *, depth: int = 0) -> object:
    """Return types, keys, and lengths. String and number values are omitted."""

    if depth > 5:
        return {"type": "nested"}
    if isinstance(value, dict):
        return {str(key): describe(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        first = describe(value[0], depth=depth + 1) if value else None
        return {"type": "list", "length": len(value), "first_item": first}
    if isinstance(value, str):
        return {"type": "str", "length": len(value)}
    if isinstance(value, bool):
        return {"type": "bool"}
    if value is None:
        return {"type": "null"}
    return {"type": type(value).__name__}


def public_scalar(key: str, value: object, *, allow: frozenset[str], secret: str) -> str | None:
    """Return a short public field, never an address or the API key."""

    if key not in allow:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str) and 1 <= len(value) <= 32 and "\n" not in value:
        if secret and secret in value:
            return None
        if _ADDRESS.fullmatch(value):
            return None
        return value
    return None


def assert_report_is_safe(report: str, secret: str) -> str:
    if secret and secret in report:
        raise GMGNError("Refusing to print a GMGN report that contains the API key.")
    return report
