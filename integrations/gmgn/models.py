"""Response objects for documented GMGN read routes.

Fields that the skill pages name are optional. A missing field stays missing.
Unknown fields are kept on the model and are not given a meaning here. Money
and token quantities are ``Decimal`` when GMGN sends a string or an integer.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, ValidationError

from integrations.gmgn.errors import GMGNResponseError


def _as_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError("boolean is not a decimal")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("invalid decimal") from exc
    raise ValueError("unsupported decimal")


def _as_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not an int")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lstrip("-").isdigit():
            return int(stripped)
    raise ValueError("unsupported int")


def _as_loose(value: object) -> str | int | bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool | int | str):
        return value
    raise ValueError("unsupported scalar")


def _as_bool(value: object) -> bool | None:
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
    raise ValueError("unsupported boolean")


FlexibleDecimal = Annotated[Decimal | None, BeforeValidator(_as_decimal)]
FlexibleInt = Annotated[int | None, BeforeValidator(_as_int)]
FlexibleBool = Annotated[bool | None, BeforeValidator(_as_bool)]
LooseScalar = Annotated[str | int | bool | None, BeforeValidator(_as_loose)]


class _GMGNModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class TokenPriceStats(_GMGNModel):
    price: FlexibleDecimal = None


class TokenPoolSummary(_GMGNModel):
    pool_address: str | None = None
    quote_address: str | None = None
    quote_symbol: str | None = None
    exchange: str | None = None
    liquidity: FlexibleDecimal = None
    base_reserve: FlexibleDecimal = None
    quote_reserve: FlexibleDecimal = None
    fee_ratio: FlexibleDecimal = None
    creation_timestamp: FlexibleInt = None


class TokenDeveloper(_GMGNModel):
    creator_address: str | None = None
    creator_token_balance: FlexibleDecimal = None
    creator_token_status: str | None = None
    top_10_holder_rate: FlexibleDecimal = None
    creator_open_count: FlexibleInt = None
    fund_from: str | None = None
    fund_from_ts: FlexibleInt = None


class TokenStat(_GMGNModel):
    holder_count: FlexibleInt = None
    top_10_holder_rate: FlexibleDecimal = None
    dev_team_hold_rate: FlexibleDecimal = None
    creator_hold_rate: FlexibleDecimal = None
    top_rat_trader_percentage: FlexibleDecimal = None
    top_bundler_trader_percentage: FlexibleDecimal = None
    fresh_wallet_rate: FlexibleDecimal = None


class WalletTagStat(_GMGNModel):
    smart_wallets: FlexibleInt = None
    renowned_wallets: FlexibleInt = None
    sniper_wallets: FlexibleInt = None
    rat_trader_wallets: FlexibleInt = None
    bundler_wallets: FlexibleInt = None
    whale_wallets: FlexibleInt = None
    fresh_wallets: FlexibleInt = None


class TokenInfo(_GMGNModel):
    address: str | None = None
    symbol: str | None = None
    name: str | None = None
    decimals: FlexibleInt = None
    total_supply: FlexibleDecimal = None
    circulating_supply: FlexibleDecimal = None
    max_supply: FlexibleDecimal = None
    liquidity: FlexibleDecimal = None
    holder_count: FlexibleInt = None
    price: TokenPriceStats | None = None
    creation_timestamp: FlexibleInt = None
    open_timestamp: FlexibleInt = None
    biggest_pool_address: str | None = None
    launchpad: str | None = None
    launchpad_status: FlexibleInt = None
    launchpad_platform: str | None = None
    ath_price: FlexibleDecimal = None
    pool: TokenPoolSummary | None = None
    dev: TokenDeveloper | None = None
    stat: TokenStat | None = None
    wallet_tags_stat: WalletTagStat | None = None


class TokenSecurity(_GMGNModel):
    is_honeypot: LooseScalar = None
    open_source: LooseScalar = None
    owner_renounced: LooseScalar = None
    renounced_mint: FlexibleBool = None
    renounced_freeze_account: FlexibleBool = None
    buy_tax: FlexibleDecimal = None
    sell_tax: FlexibleDecimal = None
    top_10_holder_rate: FlexibleDecimal = None
    dev_team_hold_rate: FlexibleDecimal = None
    creator_balance_rate: FlexibleDecimal = None
    creator_token_status: str | None = None
    suspected_insider_hold_rate: FlexibleDecimal = None
    rug_ratio: FlexibleDecimal = None
    is_wash_trading: FlexibleBool = None
    rat_trader_amount_rate: FlexibleDecimal = None
    bundler_trader_amount_rate: FlexibleDecimal = None
    sniper_count: FlexibleInt = None
    burn_status: str | None = None


class TokenPool(_GMGNModel):
    address: str | None = None
    base_address: str | None = None
    quote_address: str | None = None
    exchange: str | None = None
    liquidity: FlexibleDecimal = None
    base_reserve: FlexibleDecimal = None
    quote_reserve: FlexibleDecimal = None
    price: FlexibleDecimal = None
    creation_timestamp: FlexibleInt = None


class Candle(_GMGNModel):
    time: FlexibleInt = None
    open: FlexibleDecimal = None
    close: FlexibleDecimal = None
    high: FlexibleDecimal = None
    low: FlexibleDecimal = None
    volume: FlexibleDecimal = None
    amount: FlexibleDecimal = None


class TrendingToken(_GMGNModel):
    address: str | None = None
    symbol: str | None = None
    name: str | None = None
    chain: str | None = None
    price: FlexibleDecimal = None
    market_cap: FlexibleDecimal = None
    liquidity: FlexibleDecimal = None
    volume: FlexibleDecimal = None
    holder_count: FlexibleInt = None
    creator: str | None = None
    launchpad_platform: str | None = None
    exchange: str | None = None
    creation_timestamp: FlexibleInt = None
    open_timestamp: FlexibleInt = None
    rank: FlexibleInt = None
    hot_level: FlexibleInt = None
    price_change_percent: FlexibleDecimal = None


class LaunchToken(_GMGNModel):
    address: str | None = None
    symbol: str | None = None
    name: str | None = None
    launchpad_platform: str | None = None
    exchange: str | None = None
    usd_market_cap: FlexibleDecimal = None
    liquidity: FlexibleDecimal = None
    created_timestamp: FlexibleInt = None
    holder_count: FlexibleInt = None
    renounced_mint: FlexibleBool = None
    renounced_freeze_account: FlexibleBool = None
    rug_ratio: FlexibleDecimal = None
    sniper_count: FlexibleInt = None
    burn_status: str | None = None


class TokenParticipant(_GMGNModel):
    """One row from token holders or token traders. The skill page uses one field list."""

    address: str | None = None
    amount_percentage: FlexibleDecimal = None
    usd_value: FlexibleDecimal = None
    balance: FlexibleDecimal = None
    profit: FlexibleDecimal = None
    realized_profit: FlexibleDecimal = None
    unrealized_profit: FlexibleDecimal = None
    is_suspicious: FlexibleBool = None


class SearchCoin(_GMGNModel):
    chain: str | None = None
    address: str | None = None
    name: str | None = None
    symbol: str | None = None


class SearchWallet(_GMGNModel):
    address: str | None = None
    chain: str | None = None


class MarketSearch(_GMGNModel):
    coins: list[SearchCoin]
    wallets: list[SearchWallet]


class WalletActivity(_GMGNModel):
    activities: list[dict[str, Any]]
    next: str | None = None


class WalletProfit(_GMGNModel):
    wallet_address: str | None = None
    realized_profit: FlexibleDecimal = None
    unrealized_profit: FlexibleDecimal = None
    total_profit: FlexibleDecimal = None
    total_cost: FlexibleDecimal = None
    buy: FlexibleInt = None
    sell: FlexibleInt = None


class WalletStats(_GMGNModel):
    realized_profit: FlexibleDecimal = None
    unrealized_profit: FlexibleDecimal = None
    winrate: FlexibleDecimal = None
    total_cost: FlexibleDecimal = None
    buy_count: FlexibleInt = None
    sell_count: FlexibleInt = None
    pnl: FlexibleDecimal = None


class CreatedToken(_GMGNModel):
    token_address: str | None = None
    symbol: str | None = None
    chain: str | None = None
    market_cap: FlexibleDecimal = None
    token_ath_mc: FlexibleDecimal = None
    is_open: FlexibleBool = None
    holders: FlexibleInt = None


class CreatedTokens(_GMGNModel):
    inner_count: FlexibleInt = None
    open_count: FlexibleInt = None
    open_ratio: FlexibleDecimal = None
    tokens: list[CreatedToken]


class Retrieved[T]:
    """One successful read and the time CYVORA received it."""

    def __init__(self, route: str, retrieved_at: datetime, payload: T) -> None:
        self.route = route
        self.retrieved_at = retrieved_at
        self.payload = payload


def parse_model[T: _GMGNModel](model: type[T], data: object, route: str) -> T:
    if not isinstance(data, dict):
        raise GMGNResponseError(route, f"expected an object, got {type(data).__name__}")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise GMGNResponseError(route, _validation_detail(exc)) from None


def parse_rows[T: _GMGNModel](model: type[T], rows: object, route: str) -> list[T]:
    if not isinstance(rows, list):
        raise GMGNResponseError(route, f"expected a list, got {type(rows).__name__}")
    parsed: list[T] = []
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            raise GMGNResponseError(route, f"item {index} is {type(item).__name__}")
        try:
            parsed.append(model.model_validate(item))
        except ValidationError as exc:
            raise GMGNResponseError(route, f"item {index}: {_validation_detail(exc)}") from None
    return parsed


def object_list(data: object, *keys: str) -> list[object] | None:
    """Return the first documented list container, or None when the shape differs."""

    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for nested in ("list", "rank", "tokens"):
                inner = value.get(nested)
                if isinstance(inner, list):
                    return inner
    return None


def _validation_detail(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"])
        parts.append(f"{location}: {error['type']}")
    return "; ".join(parts) if parts else "validation failed"
