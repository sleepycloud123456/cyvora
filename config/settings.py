"""Process configuration loaded from the environment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from domain.enums import ExecutionMode
from domain.exceptions import ConfigurationError

APP_NAME = "CYVORA"
APP_VERSION = "0.1.0"
PHASE = "1"

_LIVE_MODES = frozenset({"LIVE", "LIVE_LOCKED", "LIVE_AUTHORIZED"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class Settings(BaseSettings):
    """Local runtime settings.

    Live execution modes are not represented here. Supplying one is a
    configuration error so the process fails closed.
    """

    model_config = SettingsConfigDict(
        env_prefix="CYVORA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local"] = "local"
    execution_mode: ExecutionMode = ExecutionMode.READ_ONLY
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8787, ge=1, le=65535)
    database_url: str | None = None
    log_level: str = "INFO"
    log_dir: Path = Path("logs")

    @field_validator("execution_mode", mode="before")
    @classmethod
    def reject_live_execution(cls, value: object) -> object:
        if isinstance(value, ExecutionMode):
            return value
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper()
        if normalized in _LIVE_MODES:
            raise ValueError(
                "Live execution modes are disabled. CYVORA accepts only READ_ONLY or PAPER."
            )
        return normalized

    @field_validator("api_host")
    @classmethod
    def require_loopback_host(cls, value: str) -> str:
        normalized = value.strip()
        if normalized.lower() == "localhost":
            return "localhost"
        if normalized not in _LOOPBACK_HOSTS:
            raise ValueError(
                "CYVORA_API_HOST must be a loopback address (127.0.0.1, localhost, or ::1)."
            )
        return normalized

    @field_validator("database_url", mode="before")
    @classmethod
    def blank_database_url_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def require_postgresql_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError(
                "CYVORA_DATABASE_URL must start with postgresql:// or postgresql+psycopg://."
            )
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("log_level")
    @classmethod
    def require_known_log_level(cls, value: str) -> str:
        if value not in _LOG_LEVELS:
            allowed = ", ".join(sorted(_LOG_LEVELS))
            raise ValueError(f"CYVORA_LOG_LEVEL must be one of: {allowed}.")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings, cached for the lifetime of the process."""

    return Settings()


def assert_runtime_safe(settings: Settings) -> None:
    """Repeat the fail-closed checks at process startup."""

    if settings.execution_mode not in {ExecutionMode.READ_ONLY, ExecutionMode.PAPER}:
        raise ConfigurationError("Live execution is disabled.")
    if settings.api_host not in _LOOPBACK_HOSTS:
        raise ConfigurationError("Refusing to bind a non-loopback API host.")
    if settings.environment != "local":
        raise ConfigurationError("Phase 1 only runs with CYVORA_ENVIRONMENT=local.")
