"""Paper trading profiles. A profile cannot change Shield or enable live trading."""

from __future__ import annotations

import re

from domain.exceptions import TradingValidationError
from domain.terminal import (
    AUTHORITY_NOTE,
    CRITICAL_NOTIFICATIONS,
    NotificationCategory,
    NotificationPreferences,
    TradingProfile,
)
from intelligence.numbers import as_decimal, format_decimal

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
_SECRET_WORDS = ("private", "seed", "password", "api_key", "secret", "mnemonic", "telegram")
_ALL = tuple(item.value for item in NotificationCategory)


def default_profile() -> TradingProfile:
    return TradingProfile(
        profile_id="paper-default",
        name="Paper default",
        strategy_ids=(),
        signal_threshold=None,
        active=True,
        live_trading_enabled=False,
        authority_note=AUTHORITY_NOTE,
    )


def default_preferences() -> NotificationPreferences:
    return NotificationPreferences(
        enabled_categories=_ALL,
        quiet_start_minute=None,
        quiet_end_minute=None,
        minimum_repeat_seconds=3600,
        telegram_delivery=False,
        live_trading_enabled=False,
    )


def normalize_profile(
    profile_id: str,
    name: str,
    strategy_ids: tuple[str, ...] | list[str],
    *,
    active: bool,
    signal_threshold: str | None = None,
    live_trading_enabled: bool = False,
) -> TradingProfile:
    """Accept a name and strategy list. Risk limits are not fields on a profile."""

    if live_trading_enabled:
        raise TradingValidationError("A trading profile cannot enable live trading.")
    identifier = profile_id.strip()
    if _PROFILE_ID.fullmatch(identifier) is None:
        raise TradingValidationError(
            "A profile id must be 2 to 41 characters of lowercase letters, digits, _ or -."
        )
    label = " ".join(name.split())
    if not label or len(label) > 64:
        raise TradingValidationError("A profile name must be 1 to 64 characters.")
    _reject_secret(label)
    if len(strategy_ids) > 20:
        raise TradingValidationError("A profile can list at most 20 strategy ids.")
    cleaned: list[str] = []
    for raw in strategy_ids:
        strategy_id = raw.strip()
        if _PROFILE_ID.fullmatch(strategy_id) is None:
            raise TradingValidationError("A profile strategy id is not valid.")
        _reject_secret(strategy_id)
        if strategy_id not in cleaned:
            cleaned.append(strategy_id)
    return TradingProfile(
        profile_id=identifier,
        name=label,
        strategy_ids=tuple(cleaned),
        signal_threshold=_threshold(signal_threshold),
        active=active,
        live_trading_enabled=False,
        authority_note=AUTHORITY_NOTE,
    )


def normalize_preferences(
    *,
    enabled_categories: tuple[str, ...] | list[str],
    quiet_start_minute: int | None,
    quiet_end_minute: int | None,
    minimum_repeat_seconds: int,
    telegram_delivery: bool = False,
    live_trading_enabled: bool = False,
) -> NotificationPreferences:
    """Store local delivery rules. Telegram and live trading stay off."""

    if live_trading_enabled:
        raise TradingValidationError("Notification settings cannot enable live trading.")
    if telegram_delivery:
        raise TradingValidationError("Telegram delivery is not configured. No bot token is loaded.")
    if (quiet_start_minute is None) != (quiet_end_minute is None):
        raise TradingValidationError("A quiet period needs both a start and an end minute.")
    for minute in (quiet_start_minute, quiet_end_minute):
        if minute is not None and not 0 <= minute <= 1439:
            raise TradingValidationError("A quiet-period minute must be from 0 through 1439.")
    if not 60 <= minimum_repeat_seconds <= 86400:
        raise TradingValidationError("The repeat interval must be from 60 to 86400 seconds.")
    known = set(_ALL)
    selected: list[str] = []
    for category in enabled_categories:
        if category not in known:
            raise TradingValidationError("Unknown notification category.")
        if category not in selected:
            selected.append(category)
    for category in CRITICAL_NOTIFICATIONS:
        if category.value not in selected:
            selected.append(category.value)
    return NotificationPreferences(
        enabled_categories=tuple(selected),
        quiet_start_minute=quiet_start_minute,
        quiet_end_minute=quiet_end_minute,
        minimum_repeat_seconds=minimum_repeat_seconds,
        telegram_delivery=False,
        live_trading_enabled=False,
    )


def _threshold(value: str | None) -> str | None:
    """Keep a recorded threshold. Radar and Shield do not read it."""

    if value is None or value.strip() == "":
        return None
    parsed = as_decimal(value)
    if parsed is None or parsed < 0 or parsed > 1:
        raise TradingValidationError("A recorded signal threshold must be from 0 to 1.")
    return format_decimal(parsed)


def _reject_secret(value: str) -> None:
    lowered = value.lower()
    if any(word in lowered for word in _SECRET_WORDS):
        raise TradingValidationError("A profile cannot store secret material.")
