"""Opt-in live read against GMGN. The default test run skips this."""

from __future__ import annotations

import json
import os

import pytest

from config.settings import get_settings
from integrations.gmgn.client import client_from_settings


@pytest.mark.asyncio
async def test_opt_in_readonly_rank_call() -> None:
    if os.environ.get("CYVORA_GMGN_LIVE_SMOKE") != "1":
        pytest.skip("Set CYVORA_GMGN_LIVE_SMOKE=1 to run one read-only GMGN call.")
    get_settings.cache_clear()
    settings = get_settings()
    if settings.gmgn_api_key is None:
        pytest.skip("GMGN_API_KEY is not set, so GMGN was not contacted.")
    client = client_from_settings(settings)
    async with client:
        data = await client.get_data(
            "GET",
            "/v1/market/rank",
            {"chain": "sol", "interval": "1h", "limit": 1},
        )
    assert isinstance(data, dict)
    assert isinstance(data.get("rank"), list)
    secret = settings.gmgn_api_key.get_secret_value()
    if secret in json.dumps(data):
        raise AssertionError("live response contained the API key")
