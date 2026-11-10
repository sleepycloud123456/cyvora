"""Configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from config.settings import Settings
from domain.enums import ExecutionMode


def test_defaults_are_read_only_and_loopback() -> None:
    settings = Settings(_env_file=None)
    assert settings.execution_mode is ExecutionMode.READ_ONLY
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8787
    assert settings.database_url is None
    assert settings.environment == "local"


def test_env_file_can_select_paper_mode(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("CYVORA_EXECUTION_MODE=PAPER\nCYVORA_API_PORT=8791\n", encoding="utf-8")
    settings = Settings(_env_file=env_file)
    assert settings.execution_mode is ExecutionMode.PAPER
    assert settings.api_port == 8791


def test_blank_database_url_is_unset() -> None:
    settings = Settings(_env_file=None, database_url="  ")
    assert settings.database_url is None


def test_sqlite_url_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite:///cyvora.db")


def test_public_host_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, api_host="0.0.0.0")


def test_localhost_is_normalized() -> None:
    settings = Settings(_env_file=None, api_host="LocalHost")
    assert settings.api_host == "localhost"


def test_unknown_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="verbose")
