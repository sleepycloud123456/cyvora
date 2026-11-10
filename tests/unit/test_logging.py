"""Logging writes records and does not need a secret to do so."""

from __future__ import annotations

from pathlib import Path

from config.settings import Settings
from monitoring.logging import configure_logging


def test_log_file_receives_records(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, log_dir=tmp_path, log_level="INFO")
    logger = configure_logging(settings)
    logger.info("foundation ready")
    text = (tmp_path / "cyvora.log").read_text(encoding="utf-8")
    assert "foundation ready" in text
    assert "INFO" in text


def test_log_line_redacts_the_api_key_and_database_password(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        log_dir=tmp_path,
        gmgn_api_key="gmgn-test-key-not-real",
        database_url="postgresql+psycopg://cyvora:super-secret-pass@127.0.0.1:5432/cyvora",
    )
    logger = configure_logging(settings)
    logger.error(
        "leaked GMGN_API_KEY=gmgn-test-key-not-real "
        "url=postgresql+psycopg://cyvora:super-secret-pass@127.0.0.1:5432/cyvora"
    )
    text = (tmp_path / "cyvora.log").read_text(encoding="utf-8")
    assert "gmgn-test-key-not-real" not in text
    assert "super-secret-pass" not in text
    assert "***" in text
