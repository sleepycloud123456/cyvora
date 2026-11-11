"""Opt-in live radar cycle. The default test run does not call GMGN."""

from __future__ import annotations

import os

import pytest

from config.settings import get_settings
from database.repositories.radar import PostgresRadarRepository
from intelligence.cycle import run_radar_cycle


@pytest.mark.asyncio
async def test_live_radar_cycle_when_requested() -> None:
    if os.environ.get("CYVORA_RADAR_LIVE") != "1":
        pytest.skip("Set CYVORA_RADAR_LIVE=1 to run one read-only radar cycle.")
    get_settings.cache_clear()
    settings = get_settings()
    if settings.gmgn_api_key is None or not settings.database_url:
        pytest.skip("GMGN and PostgreSQL are not both configured.")
    result = await run_radar_cycle(settings, PostgresRadarRepository(settings))
    assert result.cycle_id is not None
    assert result.analysed_count >= 1
    assert result.status in {"completed", "partial"}
    report = result.public_report()
    assert "entry=not_authorized" in report
    assert "GMGN_API_KEY" not in report
