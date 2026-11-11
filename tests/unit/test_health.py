"""Health collection and the loopback API."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.errors import unexpected_error_response
from apps.api.main import create_app
from config.settings import APP_NAME, Settings
from monitoring.health import probe_tcp


def test_health_reports_unconfigured_database(tmp_path: Path) -> None:
    secret = "local-health-token"
    app = create_app(Settings(_env_file=None, log_dir=tmp_path, api_token=secret))
    client = TestClient(app)
    live = client.get("/health")
    assert live.status_code == 200
    assert live.json() == {"status": "live"}
    assert "kill_switch" not in live.text
    response = client.get("/health", headers={"Authorization": f"Bearer {secret}"})
    assert response.status_code == 200
    body = response.json()
    assert body["app_name"] == APP_NAME
    assert body["phase"] == "9"
    assert body["kill_switch"]["state"] == "not_configured"
    assert body["live_trading_enabled"] is False
    assert body["execution_mode"] == "READ_ONLY"
    assert body["status"] == "ok"
    assert body["database"]["state"] == "not_configured"
    assert body["backend"]["state"] == "running"
    assert body["gmgn"]["state"] == "not_configured"
    assert "portfolio" not in response.text.lower()


def test_health_hides_a_configured_gmgn_key(tmp_path: Path) -> None:
    secret = "local-health-token"
    settings = Settings(
        _env_file=None,
        log_dir=tmp_path,
        api_token=secret,
        gmgn_api_key="gmgn-test-key-not-real",
    )
    response = TestClient(create_app(settings)).get(
        "/health", headers={"Authorization": f"Bearer {secret}"}
    )
    assert response.status_code == 200
    assert response.json()["gmgn"]["state"] == "configured"
    assert "gmgn-test-key-not-real" not in response.text
    log_text = (tmp_path / "cyvora.log").read_text(encoding="utf-8")
    assert "gmgn-test-key-not-real" not in log_text
    assert "gmgn=configured" in log_text


def test_health_degrades_when_database_is_unreachable(tmp_path: Path) -> None:
    secret = "local-health-token"
    settings = Settings(
        _env_file=None,
        log_dir=tmp_path,
        api_token=secret,
        database_url="postgresql+psycopg://cyvora:super-secret@127.0.0.1:1/cyvora",
    )
    client = TestClient(create_app(settings))
    live = client.get("/health")
    assert live.status_code == 200
    assert live.json() == {"status": "live"}
    assert "super-secret" not in live.text
    response = client.get("/health", headers={"Authorization": f"Bearer {secret}"})
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"]["state"] == "unreachable"
    assert "super-secret" not in response.text


def test_detailed_health_does_not_clear_the_failure_window(tmp_path: Path) -> None:
    secret = "local-health-token"
    app = create_app(
        Settings(_env_file=None, log_dir=tmp_path, api_token=secret, auth_failure_limit=3)
    )
    now = time.monotonic()
    app.state.auth_gate.restore_failures(2, now)
    client = TestClient(app)
    detailed = client.get("/health", headers={"Authorization": f"Bearer {secret}"})
    assert detailed.status_code == 200
    assert app.state.auth_gate.limited(time.monotonic()) is False
    assert (
        client.get("/trading/orders", headers={"Authorization": "Bearer nope"}).status_code == 401
    )
    assert app.state.auth_gate.limited(time.monotonic()) is True


def test_unknown_route_is_not_rewritten_as_internal_error(tmp_path: Path) -> None:
    app = create_app(Settings(_env_file=None, log_dir=tmp_path))
    client = TestClient(app)
    response = client.get("/not-a-route")
    assert response.status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_unexpected_error_response_hides_exception_text() -> None:
    secret = "super-secret-token"
    response = unexpected_error_response(RuntimeError(secret), "/health")
    assert response.status_code == 500
    assert secret not in bytes(response.body).decode()


@pytest.mark.asyncio
async def test_probe_tcp_reports_a_closed_port() -> None:
    assert await probe_tcp("127.0.0.1", 1, timeout=0.5) is False
