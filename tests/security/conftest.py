"""Security-test isolation from local environment variables."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from config.settings import get_settings


@pytest.fixture(autouse=True)
def clear_cyvora_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in list(os.environ):
        if key.startswith("CYVORA_"):
            monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
