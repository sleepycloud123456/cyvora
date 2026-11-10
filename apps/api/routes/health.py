"""Health route."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from apps.api.dependencies import get_app_settings
from apps.api.schemas.health import HealthResponse
from config.settings import Settings
from monitoring.health import collect_status, overall_status

router = APIRouter(tags=["health"])
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


@router.get("/health", response_model=HealthResponse)
def health(response: Response, settings: SettingsDep) -> HealthResponse:
    """Report process, mode, and database status.

    This route does not read a wallet or a market-data provider.
    """

    snapshot = collect_status(settings, probe_backend=False)
    payload = HealthResponse.from_snapshot(snapshot)
    if overall_status(snapshot) != "ok":
        response.status_code = 503
    return payload
