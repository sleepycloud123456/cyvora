"""Terminal reads and paper controls. No route enables live trading."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.api.auth import require_local_token
from apps.api.dependencies import get_app_settings
from config.settings import Settings
from database.repositories.terminal import PostgresTerminalRepository
from domain.exceptions import (
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    TradingDisabled,
    TradingValidationError,
)
from domain.status import StatusSnapshot
from domain.terminal import NotificationPreferences, TerminalSnapshot, TradingProfile
from monitoring.health import collect_status
from terminal.present import snapshot_payload
from terminal.profiles import normalize_preferences, normalize_profile

router = APIRouter(dependencies=[Depends(require_local_token)], tags=["terminal"])
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


class TerminalApi(Protocol):
    """The store the route calls. Tests can substitute one."""

    def load(self, status: StatusSnapshot | None, now: datetime) -> TerminalSnapshot:
        """Return the current paper terminal snapshot."""

    def save_profile(
        self,
        profile_id: str,
        name: str,
        strategy_ids: tuple[str, ...],
        *,
        active: bool,
        signal_threshold: str | None,
        now: datetime,
    ) -> TradingProfile:
        """Store one paper profile."""

    def activate_profile(self, profile_id: str, now: datetime) -> None:
        """Select one stored profile."""

    def save_preferences(self, preferences: NotificationPreferences, now: datetime) -> None:
        """Store local notification rules."""

    def pause_entries(self, now: datetime) -> None:
        """Pause new paper entries."""

    def resume_entries(self, now: datetime) -> None:
        """Resume paper entry evaluation when Shield allows it."""


class ProfileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    name: str
    strategy_ids: list[str] = Field(default_factory=list)
    signal_threshold: str | None = None
    active: bool = False
    live_trading_enabled: bool = False

    @model_validator(mode="after")
    def lock_live(self) -> ProfileBody:
        if self.live_trading_enabled:
            raise ValueError("Live trading cannot be enabled.")
        return self


class PreferenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled_categories: list[str]
    quiet_start_minute: int | None = None
    quiet_end_minute: int | None = None
    minimum_repeat_seconds: int
    telegram_delivery: bool = False
    live_trading_enabled: bool = False

    @model_validator(mode="after")
    def lock_delivery(self) -> PreferenceBody:
        if self.live_trading_enabled:
            raise ValueError("Live trading cannot be enabled.")
        if self.telegram_delivery:
            raise ValueError("Telegram delivery is not configured. No bot token is loaded.")
        return self


@router.get("/terminal/snapshot")
def read_snapshot(request: Request, settings: SettingsDep) -> dict[str, object]:
    snapshot = _call(lambda: _repository(request, settings).load(_status(settings), _now(request)))
    return snapshot_payload(snapshot)


@router.put("/terminal/profiles")
def put_profile(body: ProfileBody, request: Request, settings: SettingsDep) -> dict[str, object]:
    profile = _call(
        lambda: normalize_profile(
            body.profile_id,
            body.name,
            tuple(body.strategy_ids),
            active=body.active,
            signal_threshold=body.signal_threshold,
            live_trading_enabled=False,
        )
    )
    _call(
        lambda: _repository(request, settings).save_profile(
            body.profile_id,
            body.name,
            tuple(body.strategy_ids),
            active=body.active,
            signal_threshold=body.signal_threshold,
            now=_now(request),
        )
    )
    return {
        "profile_id": profile.profile_id,
        "live_trading_enabled": False,
        "authority_note": profile.authority_note,
    }


@router.post("/terminal/profiles/{profile_id}/activate")
def activate_profile(profile_id: str, request: Request, settings: SettingsDep) -> dict[str, bool]:
    _call(lambda: _repository(request, settings).activate_profile(profile_id, _now(request)))
    return {"active": True, "live_trading_enabled": False}


@router.put("/terminal/notifications/preferences")
def put_preferences(
    body: PreferenceBody, request: Request, settings: SettingsDep
) -> dict[str, bool]:
    preferences = _call(
        lambda: normalize_preferences(
            enabled_categories=tuple(body.enabled_categories),
            quiet_start_minute=body.quiet_start_minute,
            quiet_end_minute=body.quiet_end_minute,
            minimum_repeat_seconds=body.minimum_repeat_seconds,
            telegram_delivery=False,
            live_trading_enabled=False,
        )
    )
    _call(lambda: _repository(request, settings).save_preferences(preferences, _now(request)))
    return {"telegram_delivery": False, "live_trading_enabled": False}


@router.post("/terminal/controls/pause")
def pause(request: Request, settings: SettingsDep) -> dict[str, object]:
    _call(lambda: _repository(request, settings).pause_entries(_now(request)))
    return {"halt_entries": True, "live_trading_enabled": False, "order_submitted": False}


@router.post("/terminal/controls/resume")
def resume(request: Request, settings: SettingsDep) -> dict[str, object]:
    _call(lambda: _repository(request, settings).resume_entries(_now(request)))
    return {"halt_entries": False, "live_trading_enabled": False, "order_submitted": False}


def _repository(request: Request, settings: Settings) -> TerminalApi:
    injected = getattr(request.app.state, "terminal_repository", None)
    if injected is not None:
        return injected
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    return PostgresTerminalRepository(settings)


def _now(request: Request) -> datetime:
    injected = getattr(request.app.state, "terminal_clock", None)
    if callable(injected):
        current = injected()
        if isinstance(current, datetime):
            return current
    return datetime.now(UTC)


def _status(settings: Settings) -> StatusSnapshot:
    return collect_status(settings, probe_backend=False)


def _call[T](func: Callable[[], T]) -> T:
    try:
        return func()
    except DatabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except TradingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except TradingDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
