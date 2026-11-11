"""Decimal helpers for radar scores.

Scores stay on ``Decimal`` so the same inputs always produce the same text.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def score(value: Decimal) -> Decimal:
    """Round a component to two decimal places."""

    clamped = min(Decimal(100), max(Decimal(0), value))
    return clamped.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def as_decimal(value: object) -> Decimal | None:
    """Parse a GMGN scalar. Booleans and blank strings are not numbers."""

    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation:
            return None
    return None


def format_decimal(value: Decimal | None) -> str | None:
    """Render a decimal without binary float noise or trailing zeros."""

    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def explicit_bool(value: object) -> bool | None:
    """Return a boolean only when the payload states one.

    Empty, null, and unrecognized values stay unknown. Unknown is not false.
    """

    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def show(value: object) -> str:
    """Short evidence text. Nested objects are not expanded."""

    if value is None:
        return "null"
    if isinstance(value, Decimal):
        return format_decimal(value) or "null"
    if isinstance(value, bool | int | str):
        return str(value)
    return type(value).__name__
