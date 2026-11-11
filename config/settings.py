"""Process configuration loaded from the environment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import (
    AliasChoices,
    Field,
    SecretStr,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from domain.enums import ExecutionMode
from domain.exceptions import ConfigurationError

APP_NAME = "CYVORA"
APP_VERSION = "0.9.1"
PHASE = "9"

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
    database_url: str | None = Field(default=None, repr=False)
    log_level: str = "INFO"
    log_dir: Path = Path("logs")
    gmgn_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GMGN_API_KEY", "CYVORA_GMGN_API_KEY"),
    )
    gmgn_plan: Literal["free", "plus", "pro"] = "free"
    gmgn_timeout_seconds: float = Field(default=10.0, gt=0, le=30)
    api_token: SecretStr | None = None
    radar_chain: Literal["sol"] = "sol"
    radar_rank_interval: Literal["1m", "5m", "1h", "6h", "24h"] = "1h"
    radar_trending_limit: int = Field(default=3, ge=1, le=20)
    radar_launch_limit: int = Field(default=3, ge=1, le=20)
    radar_analyse_limit: int = Field(default=2, ge=1, le=3)
    radar_budget_weight: int = Field(default=30, ge=10, le=80)
    radar_scan_interval_seconds: int = Field(default=120, ge=60, le=3600)
    radar_kline_resolution: Literal["1m", "5m", "15m", "1h"] = "1m"
    radar_kline_lookback_seconds: int = Field(default=7200, ge=300, le=86400)
    radar_market_retention_days: int = Field(default=90, ge=7, le=3650)
    worker_stale_after_seconds: int = Field(default=900, ge=60, le=86400)
    worker_restart_limit: int = Field(default=2, ge=0, le=10)
    backup_dir: Path = Path("backups")
    diagnostics_dir: Path = Path("diagnostics")
    backup_files_kept: int = Field(default=7, ge=1, le=100)
    log_retention_days: int = Field(default=14, ge=1, le=3650)
    auth_failure_limit: int = Field(default=8, ge=3, le=50)

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

    @field_validator("gmgn_api_key", mode="before")
    @classmethod
    def blank_api_key_is_unset(cls, value: object) -> object:
        if value is None:
            return None
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(raw, str) and raw.strip() == "":
            return None
        if isinstance(raw, str):
            return raw.strip()
        return value

    @field_validator("gmgn_plan", mode="before")
    @classmethod
    def normalize_gmgn_plan(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_serializer("gmgn_api_key", "api_token")
    @classmethod
    def serialize_secret(cls, value: SecretStr | None) -> str | None:
        if value is None:
            return None
        return "configured"

    @field_serializer("database_url")
    @classmethod
    def serialize_database_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return "configured"

    @field_validator("api_token", mode="before")
    @classmethod
    def blank_api_token_is_unset(cls, value: object) -> object:
        if value is None:
            return None
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(raw, str) and raw.strip() == "":
            return None
        if isinstance(raw, str):
            return raw.strip()
        return value

    @field_validator("api_token")
    @classmethod
    def require_api_token_length(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        if len(value.get_secret_value()) < 16:
            raise ValueError("CYVORA_API_TOKEN must be at least 16 characters.")
        return value

    @model_validator(mode="after")
    def radar_budget_covers_discovery_and_core_reads(self) -> Settings:
        """Keep a cycle inside a weight budget that can finish the core reads.

        Discovery is weight 5. Each analysed token needs weight 5 for info,
        security, pool, and kline. Holder and trader reads are optional and
        use whatever weight remains.
        """

        needed = 5 + (self.radar_analyse_limit * 5)
        if self.radar_budget_weight < needed:
            raise ValueError(
                "CYVORA_RADAR_BUDGET_WEIGHT must cover discovery plus the core "
                "reads for CYVORA_RADAR_ANALYSE_LIMIT tokens."
            )
        return self

    @field_validator("backup_dir", "diagnostics_dir")
    @classmethod
    def require_relative_runtime_dir(cls, value: Path) -> Path:
        if value.is_absolute() or ".." in value.parts:
            raise ValueError("Backup and diagnostic directories must stay inside the workspace.")
        return value

    @field_validator("log_dir")
    @classmethod
    def reject_parent_log_dir(cls, value: Path) -> Path:
        if ".." in value.parts:
            raise ValueError("CYVORA_LOG_DIR cannot contain '..'.")
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
    """Return the process settings, cached for the lifetime of the process.

    A validation failure is re-raised without the rejected input. Pydantic's
    own error object can contain a database URL.
    """

    try:
        return Settings()
    except ValidationError as exc:
        messages = "; ".join(str(item.get("msg", "invalid setting")) for item in exc.errors())
        raise ConfigurationError(f"CYVORA settings are invalid. {messages}") from None


def assert_runtime_safe(settings: Settings) -> None:
    """Repeat the fail-closed checks at process startup."""

    if settings.execution_mode not in {ExecutionMode.READ_ONLY, ExecutionMode.PAPER}:
        raise ConfigurationError("Live execution is disabled.")
    if settings.api_host not in _LOOPBACK_HOSTS:
        raise ConfigurationError("Refusing to bind a non-loopback API host.")
    if settings.environment != "local":
        raise ConfigurationError("CYVORA only runs with CYVORA_ENVIRONMENT=local.")
