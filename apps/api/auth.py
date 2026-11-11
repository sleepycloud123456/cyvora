"""Loopback authentication for routes beyond health."""

from __future__ import annotations

import hmac
import logging
import time
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from apps.api.dependencies import get_app_settings
from config.settings import Settings
from domain.operations import AuthEvent
from operations.auth_audit import AuthGate

logger = logging.getLogger("cyvora.auth")
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def require_local_token(request: Request, settings: SettingsDep) -> None:
    """Require the local bearer token. Health does not use this dependency."""

    gate: AuthGate = request.app.state.auth_gate
    moment = datetime.now(UTC)
    if gate.limited(time.monotonic()):
        _remember(settings, gate.remember("limited", "api", moment))
        raise HTTPException(status_code=429, detail="Too many authentication failures.")
    if settings.api_token is None:
        _remember(settings, gate.remember("unconfigured", "api", moment))
        raise HTTPException(status_code=503, detail="Local API token is not configured.")
    header = request.headers.get("authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix) or not _matches(header[len(prefix) :], settings):
        gate.record_failure(time.monotonic())
        _remember(settings, gate.remember("rejected", "api", moment))
        raise HTTPException(status_code=401, detail="Unauthorized.")
    gate.record_success()
    _remember(settings, gate.remember("accepted", "api", moment))


def _matches(provided: str, settings: Settings) -> bool:
    if settings.api_token is None:
        return False
    expected = settings.api_token.get_secret_value()
    return hmac.compare_digest(
        sha256(provided.encode()).digest(), sha256(expected.encode()).digest()
    )


def _remember(settings: Settings, event: AuthEvent) -> None:
    """Keep the result in memory and, when a database exists, in auth_events.

    The token is not part of the event.
    """

    if not settings.database_url:
        return
    try:
        from database.repositories.operations import PostgresOperationsRepository

        PostgresOperationsRepository(settings).save_auth(event)
    except Exception as exc:
        logger.warning("auth event store failed error_type=%s", type(exc).__name__)
