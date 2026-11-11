"""Loopback FastAPI application."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from apps.api.errors import unexpected_error_response
from apps.api.routes.health import router as health_router
from apps.api.routes.operations import router as operations_router
from apps.api.routes.radar import router as radar_router
from apps.api.routes.simulation import router as simulation_router
from apps.api.routes.terminal import router as terminal_router
from apps.api.routes.trading import router as trading_router
from config.settings import APP_NAME, APP_VERSION, Settings, assert_runtime_safe, get_settings
from database.repositories.trading import restore_strategies
from monitoring.health import log_startup
from monitoring.logging import configure_logging
from operations.auth_audit import AuthGate
from operations.recovery import startup_recovery

logger = logging.getLogger("cyvora.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the local API. The host check happens before the app serves traffic."""

    active = settings or get_settings()
    assert_runtime_safe(active)
    configure_logging(active)
    log_startup(active)
    app = FastAPI(
        title=f"{APP_NAME} API",
        version=APP_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = active
    app.state.radar_lock = asyncio.Lock()
    app.state.auth_gate = _restored_auth_gate(active)
    app.include_router(health_router)
    app.include_router(radar_router)
    app.include_router(trading_router)
    app.include_router(simulation_router)
    app.include_router(terminal_router)
    app.include_router(operations_router)
    restore_strategies(active)
    app.state.recovery = startup_recovery(active)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        return unexpected_error_response(exc, request.url.path)

    return app


def _restored_auth_gate(active: Settings) -> AuthGate:
    """Build the failure gate and reload recent rejections when a database exists."""

    gate = AuthGate(limit=active.auth_failure_limit)
    if not active.database_url:
        return gate
    try:
        from database.repositories.operations import PostgresOperationsRepository

        count = PostgresOperationsRepository(active).recent_auth_failures(
            now=datetime.now(UTC),
            window_seconds=gate.window_seconds,
        )
    except Exception as exc:
        logger.warning("auth failure restore failed error_type=%s", type(exc).__name__)
        return gate
    gate.restore_failures(count, time.monotonic())
    return gate


def main() -> None:
    """Start the API on the configured loopback address."""

    settings = get_settings()
    assert_runtime_safe(settings)
    uvicorn.run(
        "apps.api.main:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
