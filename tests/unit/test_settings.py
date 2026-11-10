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


def test_gmgn_api_key_is_loaded_from_its_documented_name(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GMGN_API_KEY=gmgn-test-key-not-real\n", encoding="utf-8")
    settings = Settings(_env_file=env_file)
    if settings.gmgn_api_key is None:
        raise AssertionError("fixture GMGN_API_KEY was not loaded")
    loaded = settings.gmgn_api_key.get_secret_value()
    if loaded != "gmgn-test-key-not-real":
        raise AssertionError("fixture GMGN_API_KEY was not the value returned by settings")
    assert "gmgn-test-key-not-real" not in repr(settings)
    assert settings.model_dump()["gmgn_api_key"] == "configured"


def test_blank_gmgn_api_key_is_unset(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GMGN_API_KEY=\n", encoding="utf-8")
    settings = Settings(_env_file=env_file)
    assert settings.gmgn_api_key is None


def test_private_key_variable_is_ignored(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GMGN_PRIVATE_KEY=not-a-real-key\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=env_file)
    assert not hasattr(settings, "gmgn_private_key")
    assert "not-a-real-key" not in repr(settings)


def test_unknown_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="verbose")
