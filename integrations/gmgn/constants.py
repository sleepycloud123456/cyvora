"""GMGN OpenAPI facts copied from the official client.

Source checked on 2026-11-11:

- https://docs.gmgn.ai/index/gmgn-agent-api
- https://github.com/GMGNAI/gmgn-skills (``src/client/OpenApiClient.ts`` and the
  market, token, and portfolio skill pages on ``main``)

A path is listed here only when that client calls it. Weights are the skill
pages' leaky-bucket weights. The free, plus, and pro buckets are ``5/5``,
``20/20``, and ``50/50`` (refill rate / capacity).
"""

from __future__ import annotations

OFFICIAL_BASE_URL = "https://openapi.gmgn.ai"
USER_AGENT = "cyvora/0.3.0 read-only"
DOCS_VERIFIED_ON = "2026-11-11"

# Documented chains. CYVORA's product chain is Solana; the client still accepts
# the other names the official CLI validates, and rejects anything else.
CHAINS = frozenset(
    {
        "sol",
        "bsc",
        "base",
        "eth",
        "arbitrum",
        "hyperevm",
        "robinhood",
        "arc",
        "stable",
        "avalanche",
    }
)
EVM_CHAINS = frozenset({"bsc", "base", "eth", "arbitrum", "avalanche"})

RANK_INTERVALS = frozenset({"1m", "5m", "1h", "6h", "24h"})
KLINE_RESOLUTIONS = frozenset({"1s", "30s", "1m", "5m", "15m", "1h", "4h", "1d"})

HOLDER_ORDER_BY = frozenset(
    {
        "amount_percentage",
        "profit",
        "unrealized_profit",
        "buy_volume_cur",
        "sell_volume_cur",
    }
)
HOLDER_TAGS = frozenset(
    {
        "smart_degen",
        "renowned",
        "fresh_wallet",
        "dev",
        "sniper",
        "rat_trader",
        "bundler",
        "transfer_in",
        "dex_bot",
        "bluechip_owner",
    }
)
SORT_DIRECTIONS = frozenset({"asc", "desc"})
TRENDING_ORDER_BY = frozenset(
    {
        "default",
        "swaps",
        "marketcap",
        "history_highest_market_cap",
        "liquidity",
        "volume",
        "holder_count",
        "smart_degen_count",
        "renowned_count",
        "gas_fee",
        "price",
        "change1m",
        "change5m",
        "change1h",
        "creation_timestamp",
    }
)
ACTIVITY_TYPES = frozenset({"buy", "sell", "transferIn", "transferOut", "add", "remove"})
STATS_PERIODS = frozenset({"7d", "30d"})
PROFIT_PERIODS = frozenset({"1d", "7d", "30d", "all"})
CREATED_TOKEN_ORDER_BY = frozenset({"market_cap", "token_ath_mc"})
MIGRATE_STATES = frozenset({"migrated", "non_migrated"})

# (method, path) -> leaky-bucket weight for exist-auth reads.
# One-second candles are the documented exception: weight 3, Pro only.
ALLOWED_ROUTES: dict[tuple[str, str], int] = {
    ("GET", "/v1/token/info"): 1,
    ("GET", "/v1/token/security"): 1,
    ("GET", "/v1/token/pool_info"): 1,
    ("GET", "/v1/market/token_top_holders"): 5,
    ("GET", "/v1/market/token_top_traders"): 5,
    ("GET", "/v1/market/token_kline"): 2,
    ("GET", "/v1/market/rank"): 3,
    ("POST", "/v1/trenches"): 2,
    ("GET", "/v1/market/search"): 1,
    ("GET", "/v1/user/info"): 2,
    ("GET", "/v1/user/wallet_activity"): 3,
    ("GET", "/v1/user/wallet_stats"): 3,
    ("POST", "/v1/user/wallet_profits"): 3,
    ("GET", "/v1/user/wallet_token_balance"): 2,
    ("GET", "/v1/user/created_tokens"): 2,
}

# These exist in the official client. CYVORA does not call them.
# Trade routes can move funds. wallet_holdings requires a private-key signature.
FORBIDDEN_ROUTES = frozenset(
    {
        "/v1/trade/swap",
        "/v1/trade/multi_swap",
        "/v1/trade/quote",
        "/v1/trade/query_order",
        "/v1/trade/gas_price",
        "/v1/trade/follow_wallet",
        "/v1/trade/strategy/create",
        "/v1/trade/strategy/cancel",
        "/v1/trade/strategy/orders",
        "/v1/user/wallet_holdings",
        "/v1/cooking/create_token",
    }
)

PLAN_BUCKETS: dict[str, tuple[float, float]] = {
    "free": (5.0, 5.0),
    "plus": (20.0, 20.0),
    "pro": (50.0, 50.0),
}

# Official client waits at most this long before a single rate-limit retry.
RATE_LIMIT_RETRY_MAX_WAIT_SECONDS = 5.0
RATE_LIMIT_RETRY_BUFFER_SECONDS = 1.0


def route_weight(method: str, path: str, query: object) -> int:
    """Return the documented weight for an allowed route."""

    weight = ALLOWED_ROUTES[(method, path)]
    if (
        path == "/v1/market/token_kline"
        and isinstance(query, dict)
        and str(query.get("resolution", "")) == "1s"
    ):
        return 3
    return weight
