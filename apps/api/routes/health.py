"""Health route."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from apps.api.auth import allow_detailed_health
from apps.api.dependencies import get_app_settings
from apps.api.schemas.health import HealthResponse
from config.settings import Settings
from monitoring.health import collect_status, overall_status

router = APIRouter(tags=["health"])
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


@router.get("/health", response_model=None)
def health(
    request: Request, response: Response, settings: SettingsDep
) -> JSONResponse | HealthResponse:
    """Report liveness, or the detailed status when the local token is sent.

    A request without an Authorization header returns only ``{"status": "live"}``.
    This route does not read a wallet or a market-data provider.
    """

    if not allow_detailed_health(request, settings):
        return JSONResponse(content={"status": "live"})
    snapshot = collect_status(settings, probe_backend=False)
    payload = HealthResponse.from_snapshot(snapshot)
    if overall_status(snapshot) != "ok":
        response.status_code = 503
    return payload
