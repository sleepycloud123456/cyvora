"""Loopback authentication for routes beyond health."""

from __future__ import annotations

import hmac
from hashlib import sha256
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from apps.api.dependencies import get_app_settings
from config.settings import Settings

SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def require_local_token(request: Request, settings: SettingsDep) -> None:
    """Require the local bearer token. Health does not use this dependency."""

    if settings.api_token is None:
        raise HTTPException(status_code=503, detail="Local API token is not configured.")
    header = request.headers.get("authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix):
        raise HTTPException(status_code=401, detail="Unauthorized.")
    provided = header[len(prefix) :]
    expected = settings.api_token.get_secret_value()
    if not hmac.compare_digest(
        sha256(provided.encode()).digest(), sha256(expected.encode()).digest()
    ):
        raise HTTPException(status_code=401, detail="Unauthorized.")
