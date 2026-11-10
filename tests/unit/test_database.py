"""Database URL redaction and the unreachable-database report."""

from __future__ import annotations

import logging

import pytest

from config.settings import Settings
from database.connection import check_database, redact_database_url


def test_redact_database_url_hides_password() -> None:
    redacted = redact_database_url("postgresql+psycopg://cyvora:super-secret@127.0.0.1:5432/cyvora")
    assert "super-secret" not in redacted
    assert "***" in redacted
    assert "127.0.0.1" in redacted


def test_redact_database_url_keeps_url_without_credentials() -> None:
    url = "postgresql://127.0.0.1:5432/cyvora"
    assert redact_database_url(url) == url


def test_unreachable_database_does_not_echo_the_password(caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://cyvora:super-secret@127.0.0.1:1/cyvora",
    )
    with caplog.at_level(logging.DEBUG):
        status = check_database(settings)
    assert status.state == "unreachable"
    assert "super-secret" not in status.detail
    assert "super-secret" not in caplog.text
