"""Reject caller input that the documented GMGN CLI would reject."""

from __future__ import annotations

from integrations.gmgn.constants import (
    ACTIVITY_TYPES,
    CHAINS,
    CREATED_TOKEN_ORDER_BY,
    EVM_CHAINS,
    HOLDER_ORDER_BY,
    HOLDER_TAGS,
    KLINE_RESOLUTIONS,
    MIGRATE_STATES,
    PROFIT_PERIODS,
    RANK_INTERVALS,
    SORT_DIRECTIONS,
    STATS_PERIODS,
    TRENDING_ORDER_BY,
)
from integrations.gmgn.errors import GMGNValidationError

_SOL_ALPHABET = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")


def require_choice(name: str, value: str, allowed: frozenset[str]) -> str:
    if value not in allowed:
        raise GMGNValidationError(f"{name} must be one of: {', '.join(sorted(allowed))}.")
    return value


def require_chain(chain: str) -> str:
    return require_choice("chain", chain, CHAINS)


def require_address(address: str, chain: str) -> str:
    """Check the address shape the official CLI documents for the chain.

    Address formats for chains other than Solana and the listed EVM networks
    are not specified beyond a non-empty token. Those chains get a length check.
    """

    require_chain(chain)
    if any(ord(char) < 32 or ord(char) == 127 for char in address):
        raise GMGNValidationError("address contains a control character.")
    if chain == "sol":
        if not 32 <= len(address) <= 44 or any(char not in _SOL_ALPHABET for char in address):
            raise GMGNValidationError("Solana address must be 32-44 base58 characters.")
        return address
    if chain in EVM_CHAINS:
        body = address.removeprefix("0x")
        hex_ok = len(body) == 40 and all(char in "0123456789abcdefABCDEF" for char in body)
        if not (address.startswith("0x") and hex_ok):
            raise GMGNValidationError("EVM address must be 0x followed by 40 hex digits.")
        return address
    if not 1 <= len(address) <= 100 or any(char.isspace() for char in address):
        raise GMGNValidationError("address must be 1-100 characters without spaces.")
    return address


def require_interval(interval: str) -> str:
    return require_choice("interval", interval, RANK_INTERVALS)


def require_resolution(resolution: str) -> str:
    return require_choice("resolution", resolution, KLINE_RESOLUTIONS)


def require_direction(direction: str) -> str:
    return require_choice("direction", direction, SORT_DIRECTIONS)


def require_trending_order(order_by: str) -> str:
    return require_choice("order_by", order_by, TRENDING_ORDER_BY)


def require_holder_order(order_by: str) -> str:
    return require_choice("order_by", order_by, HOLDER_ORDER_BY)


def require_holder_tag(tag: str) -> str:
    return require_choice("tag", tag, HOLDER_TAGS)


def require_activity_type(activity_type: str) -> str:
    return require_choice("type", activity_type, ACTIVITY_TYPES)


def require_stats_period(period: str) -> str:
    return require_choice("period", period, STATS_PERIODS)


def require_profit_period(period: str) -> str:
    return require_choice("period", period, PROFIT_PERIODS)


def require_created_order(order_by: str) -> str:
    return require_choice("order_by", order_by, CREATED_TOKEN_ORDER_BY)


def require_migrate_state(state: str) -> str:
    return require_choice("migrate_state", state, MIGRATE_STATES)


def require_limit(limit: int, *, maximum: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= maximum:
        raise GMGNValidationError(f"limit must be an integer from 1 to {maximum}.")
    return limit


def require_search_query(query: str) -> str:
    cleaned = "".join(char for char in query if ord(char) >= 32 and ord(char) != 127)
    cleaned = cleaned.strip()
    if not 1 <= len(cleaned) <= 100:
        raise GMGNValidationError("search query must be 1-100 characters.")
    return cleaned
