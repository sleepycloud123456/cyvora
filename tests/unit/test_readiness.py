"""Phase 9 gate, kill switch, and the operator readiness report."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from config.settings import Settings
from domain.enums import ExecutionMode
from domain.exceptions import TradingDisabled
from domain.readiness import ControlCheck
from domain.trading import OrderSide, SimulationOutcome, SolanaInstrument
from readiness.gate import live_gate, standard_checks
from readiness.kill_switch import confirmation_accepted, orders_blocked
from readiness.report import build_report
from trading.execution.gateway import PaperExecutionGateway, PaperOrderRequest
from trading.memory_store import MemoryTradingStore

NOW = datetime(2026, 11, 11, tzinfo=UTC)
MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def _request(key: str = "kill-switch-1") -> PaperOrderRequest:
    instrument = SolanaInstrument(MINT, "USDC", 6, 6, "SOL", 9)
    return PaperOrderRequest(
        strategy_id="core-slot",
        instrument=instrument,
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        reference_price=Decimal("1"),
        outcome=SimulationOutcome.FILL,
        idempotency_key=key,
    )


def test_live_gate_stays_closed_when_every_check_is_marked_present() -> None:
    forced = tuple(
        ControlCheck(item.name, "present", "marked present by the test")
        for item in standard_checks()
    )
    decision = live_gate(forced)
    assert decision.authorized is False
    assert decision.live_trading_enabled is False
    assert decision.authorization_state == "not_authorized"
    assert "does not grant" in decision.reason
    report = build_report(Settings(_env_file=None))
    assert report["ready_for_live"] is False
    assert report["live_trading_enabled"] is False
    assert report["kill_switch"] == "not_configured"
    assert report["authorization_state"] == "not_authorized"
    assert "operator_decisions" in report


def test_missing_kill_switch_blocks_and_release_needs_the_confirmation_word() -> None:
    assert orders_blocked(None) is True
    assert orders_blocked(True) is True
    assert orders_blocked(False) is False
    assert confirmation_accepted("engage", "ENGAGE") is True
    assert confirmation_accepted("release", "RELEASE") is True
    assert confirmation_accepted("release", "release") is False
    assert confirmation_accepted("enable-live", "RELEASE") is False
    assert confirmation_accepted("release", "not-a-wallet-password") is False


def test_engaged_kill_switch_stores_nothing_and_a_replay_returns_the_old_order() -> None:
    store = MemoryTradingStore()
    open_gateway = PaperExecutionGateway(
        ExecutionMode.PAPER, store, lambda: NOW, entries_blocked=lambda: False
    )
    stored = open_gateway.submit(_request())
    assert stored.simulated is True
    assert stored.shield_decision != "live_approved"
    closed = PaperExecutionGateway(
        ExecutionMode.PAPER, store, lambda: NOW, entries_blocked=lambda: True
    )
    replay = closed.submit(_request())
    assert replay.client_order_id == stored.client_order_id
    assert len(store.orders) == 1
    with pytest.raises(TradingDisabled, match="kill switch"):
        closed.submit(_request("kill-switch-2"))
    assert len(store.orders) == 1


def test_readiness_route_cannot_authorize_live_trading(tmp_path: Path) -> None:
    secret = "local-test-token-ok"
    app = create_app(Settings(_env_file=None, log_dir=tmp_path, api_token=secret))
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {secret}"}
    report = client.get("/operations/readiness", headers=headers)
    assert report.status_code == 200
    body = report.json()
    assert body["ready_for_live"] is False
    assert body["live_trading_enabled"] is False
    assert body["gate"]["authorized"] is False
    assert body["kill_switch"] == "not_configured"
    names = {item["name"] for item in body["gate"]["checks"]}
    assert "wallet_compatibility" in names
    assert "balance_verification" in names
    assert "emergency_controls" in names
    engaged = client.post(
        "/operations/kill-switch/engage",
        headers=headers,
        json={"confirm": "ENGAGE"},
    )
    assert engaged.status_code == 503
    assert secret not in engaged.text
    huge = "x" * 5000
    rejected = client.get("/operations/readiness", headers={"Authorization": f"Bearer {huge}"})
    assert rejected.status_code == 401
    assert huge not in rejected.text


def test_analyst_and_resume_do_not_name_the_kill_switch_release() -> None:
    root = Path(__file__).resolve().parents[2]
    analyst = (root / "terminal" / "analyst.py").read_text(encoding="utf-8")
    shield = (root / "shield" / "engine.py").read_text(encoding="utf-8")
    assert "ReadinessRepository" not in analyst
    assert "ReadinessRepository" not in shield
    assert "RELEASE_CONFIRMATION" not in analyst
    assert "RELEASE_CONFIRMATION" not in shield
