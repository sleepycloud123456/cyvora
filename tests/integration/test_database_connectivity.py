"""Database connectivity when an operator has configured PostgreSQL."""

from __future__ import annotations

import pytest

from config.settings import get_settings
from database.connection import check_database


def test_configured_database_is_reachable() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    status = check_database(settings)
    if status.state == "not_configured":
        pytest.skip("CYVORA_DATABASE_URL is not set, so PostgreSQL was not contacted.")
    assert status.state == "reachable", status.detail
