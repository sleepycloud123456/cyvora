"""Phase 8 local operations. These tests do not call GMGN or install a service."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.desktop.windows.main_window import MainWindow
from config.settings import Settings
from domain.enums import ExecutionMode
from domain.operations import BookOrder, BookPosition, BookSnapshot, TickResult
from domain.status import ComponentStatus, StatusSnapshot
from operations.auth_audit import AuthGate
from operations.backup import run_backup
from operations.diagnostics import build_document
from operations.recovery import assess_book
from operations.retention import plan_retention
from operations.supervisor import Supervisor
from operations.workers import RadarWorker
from trading.memory_store import MemoryTradingStore

NOW = datetime(2026, 11, 11, tzinfo=UTC)
MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
PASSWORD = "dump-secret-value"


def test_recovery_does_not_treat_a_missing_book_as_flat() -> None:
    missing = assess_book(BookSnapshot("not_configured", "unread", (), (), 0, None), NOW, NOW)
    assert missing.open_positions is None
    assert missing.entries_blocked is False
    assert missing.wallet_assumed_flat is False
    assert missing.wallet_reconciliation == "not_authorized"
    assert "not assumed flat" in missing.detail

    empty = assess_book(BookSnapshot("reachable", "missing", (), (), 0, None), NOW, NOW)
    assert empty.open_positions == 0
    assert empty.entries_blocked is False
    assert empty.wallet_assumed_flat is False
    assert empty.live_trading_enabled is False


def test_recovery_blocks_a_conflicting_paper_book() -> None:
    conflict = assess_book(
        BookSnapshot(
            "reachable",
            "loaded",
            (BookOrder(MINT, "BUY", "CONFIRMED", Decimal("2")),),
            (BookPosition(MINT, Decimal("1")),),
            0,
            None,
        ),
        NOW,
        NOW,
    )
    assert conflict.entries_blocked is True
    assert conflict.position_status == "conflict"
    assert conflict.wallet_assumed_flat is False

    pending = assess_book(
        BookSnapshot(
            "reachable",
            "loaded",
            (BookOrder(MINT, "BUY", "CREATED", Decimal("0")),),
            (),
            0,
            None,
        ),
        NOW,
        NOW,
    )
    assert pending.entries_blocked is True
    assert pending.unresolved_orders == 1

    running = assess_book(BookSnapshot("reachable", "loaded", (), (), 1, None), NOW, NOW)
    assert running.entries_blocked is True


def test_matched_paper_fill_can_continue() -> None:
    report = assess_book(
        BookSnapshot(
            "reachable",
            "loaded",
            (BookOrder(MINT, "BUY", "CONFIRMED", Decimal("2")),),
            (BookPosition(MINT, Decimal("2")),),
            0,
            None,
        ),
        NOW,
        NOW,
    )
    assert report.entries_blocked is False
    assert report.position_status == "matched"
    assert report.open_positions == 1
    assert report.result == "complete"


def test_supervisor_restarts_once_and_hides_the_error_text() -> None:
    class Flaky:
        kind = "radar"

        def __init__(self) -> None:
            self.calls = 0

        def tick(self, now: datetime) -> TickResult:
            del now
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("secret-boom")
            return TickResult("radar", "ok", "done")

    flaky = Flaky()
    report = Supervisor(
        (flaky,),
        restart_limit=1,
        execution_mode=ExecutionMode.PAPER,
        clock=lambda: NOW,
    ).run(1)
    assert flaky.calls == 2
    assert report.failures == 0
    assert report.results[0].status == "ok"
    assert "secret-boom" not in report.results[0].detail

    class Boom:
        kind = "portfolio"

        def tick(self, now: datetime) -> TickResult:
            del now
            raise RuntimeError("secret-boom")

    failed = Supervisor(
        (Boom(),),
        restart_limit=0,
        execution_mode=ExecutionMode.READ_ONLY,
        clock=lambda: NOW,
    ).run(1)
    assert failed.results[0].status == "failed"
    assert failed.critical_failure is True
    assert failed.live_trading_enabled is False
    assert "secret-boom" not in failed.results[0].detail


def test_default_radar_tick_does_not_call_a_cycle() -> None:
    called = False

    def cycle(now: datetime) -> TickResult:
        nonlocal called
        del now
        called = True
        return TickResult("radar", "ok", "called")

    assert RadarWorker().tick(NOW).status == "skipped"
    assert called is False
    assert RadarWorker(cycle).tick(NOW).status == "ok"
    assert called is True


def test_backup_keeps_the_password_off_the_command(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        _env_file=None,
        log_dir=Path("logs"),
        backup_dir=Path("backups"),
        database_url=f"postgresql+psycopg://cyvora:{PASSWORD}@127.0.0.1:5432/cyvora",
    )

    def runner(argv: list[str], env: dict[str, str], destination: Path) -> int:
        assert PASSWORD not in " ".join(argv)
        assert env["PGPASSWORD"] == PASSWORD
        destination.write_bytes(b"PGDMP")
        return 0

    report = run_backup(settings, now=NOW, tool=Path("pg_dump"), runner=runner)
    assert report.status == "completed"
    assert report.file_name == "cyvora-20261111T000000Z.dump"
    assert PASSWORD not in report.detail
    assert report.live_trading_enabled is False


def test_backup_refuses_a_remote_database(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        log_dir=tmp_path,
        database_url=f"postgresql+psycopg://cyvora:{PASSWORD}@example.com:5432/cyvora",
    )
    report = run_backup(settings, now=NOW)
    assert report.status == "refused"
    assert report.file_name is None
    assert PASSWORD not in report.detail


def test_diagnostics_redact_secrets(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        log_dir=tmp_path,
        gmgn_api_key="gmgn-test-key-not-real",
        api_token="local-test-token-ok",
        database_url=f"postgresql+psycopg://cyvora:{PASSWORD}@127.0.0.1:5432/cyvora",
    )
    document = build_document(
        settings,
        recovery=None,
        run=None,
        log_text=(
            "GMGN_API_KEY=gmgn-test-key-not-real "
            f"postgresql+psycopg://cyvora:{PASSWORD}@127.0.0.1:5432/cyvora"
        ),
        generated_at=NOW,
    )
    assert "gmgn-test-key-not-real" not in document
    assert PASSWORD not in document
    assert "local-test-token-ok" not in document
    assert '"live_trading_enabled": false' in document
    assert '"cloud_deployed": false' in document


def test_retention_plan_does_not_delete_audit() -> None:
    plan = plan_retention(Settings(_env_file=None))
    assert plan.audit_events_deleted is False
    assert plan.backtests_deleted is False
    assert "Audit events are not deleted." in plan.notes


def test_auth_gate_limits_failures_without_storing_a_token() -> None:
    gate = AuthGate(limit=2, window_seconds=60)
    assert gate.limited(0) is False
    gate.record_failure(1)
    gate.record_failure(2)
    assert gate.limited(3) is True
    event = gate.remember("rejected", "api", NOW)
    assert "local-test-token-ok" not in event.detail
    assert not hasattr(event, "token")


def test_operations_routes_stay_local_and_block_entries(tmp_path: Path) -> None:
    secret = "local-test-token-ok"
    settings = Settings(
        _env_file=None,
        log_dir=tmp_path,
        api_token=secret,
        auth_failure_limit=3,
        execution_mode=ExecutionMode.PAPER,
        diagnostics_dir=Path("diagnostics"),
    )
    app = create_app(settings)
    store = MemoryTradingStore()
    app.state.trading_store = store
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["workers"]["state"] == "not_configured"
    assert health.json()["websocket"]["state"] == "not_configured"
    assert "portfolio" not in health.text.lower()
    assert client.get("/operations/status").status_code == 401
    headers = {"Authorization": f"Bearer {secret}"}
    body = client.get("/operations/status", headers=headers).json()
    assert body["live_trading_enabled"] is False
    assert body["cloud_deployed"] is False
    assert body["wallet_assumed_flat"] is False
    assert body["retention"]["audit_events_deleted"] is False
    blocked = assess_book(BookSnapshot("unreachable", "unread", (), (), 0, None), NOW, NOW)
    app.state.recovery = blocked
    refused = client.post(
        "/trading/paper/orders",
        headers=headers,
        json={
            "strategy_id": "core-slot",
            "mint": MINT,
            "symbol": "USDC",
            "side": "BUY",
            "quantity": "1",
            "reference_price": "1",
            "quote_symbol": "SOL",
            "size_decimals": 6,
            "price_decimals": 6,
            "quote_decimals": 9,
            "idempotency_key": "blocked-order",
        },
    )
    assert refused.status_code == 409
    assert store.orders == {}
    run = client.post("/operations/supervisor/run", headers=headers, json={"ticks": 1})
    assert run.status_code == 200
    payload = run.json()
    assert payload["live_trading_enabled"] is False
    assert payload["cloud_deployed"] is False
    assert {item["kind"]: item["status"] for item in payload["workers"]}["radar"] == "skipped"
    for _ in range(3):
        assert (
            client.get(
                "/operations/status", headers={"Authorization": "Bearer nope-not-the-token"}
            ).status_code
            == 401
        )
    limited = client.get(
        "/operations/status", headers={"Authorization": "Bearer nope-not-the-token"}
    )
    assert limited.status_code == 429
    assert secret not in limited.text
    assert all(secret not in event.detail for event in app.state.auth_gate.events)


def test_cloud_templates_do_not_contain_secrets() -> None:
    root = Path(__file__).resolve().parents[2]
    names = (
        root / "deploy" / "cloud" / "Dockerfile",
        root / "deploy" / "cloud" / "docker-compose.yml",
        root / "deploy" / "cloud" / ".dockerignore",
        root / "deploy" / "windows" / "cyvora-supervisor.xml",
        root / "scripts" / "register_supervisor_task.ps1",
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in names)
    lowered = text.lower()
    assert "private_key" not in lowered
    assert "begin open" not in lowered
    assert "change_me" not in lowered
    assert ".env" in (root / "deploy" / "cloud" / ".dockerignore").read_text(encoding="utf-8")
    script = (root / "scripts" / "register_supervisor_task.ps1").read_text(encoding="utf-8")
    assert "ConfirmInstall" in script
    assert "CYVORA_SERVICE_NOT_INSTALLED" in script


def test_health_page_shows_worker_state_and_reconnect(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = MainWindow(Settings(_env_file=None), start_probe=False)
    qtbot.addWidget(window)
    snapshot = StatusSnapshot(
        app_name="CYVORA",
        version="0.8.0",
        phase="8",
        environment="local",
        execution_mode="READ_ONLY",
        live_trading_enabled=False,
        application=ComponentStatus("running", "running"),
        database=ComponentStatus("not_configured", "unset"),
        backend=ComponentStatus("offline", "offline"),
        gmgn=ComponentStatus("not_configured", "unset"),
        workers=ComponentStatus("not_running", "No supervised worker has reported a heartbeat."),
        market_data=ComponentStatus("missing", "No radar cycle is stored."),
        queue=ComponentStatus("idle", "No external queue is configured."),
        websocket=ComponentStatus("not_configured", "No websocket server is configured."),
    )
    window.apply_snapshot(snapshot)
    assert window.health.workers_card.state_label.text() == "not_running"
    assert window.health.market_data_card.state_label.text() == "missing"
    assert "does not start the API" in window.health.reconnect.text()
    assert window._reconnect_timer.isActive()
    assert window._reconnect_timer.interval() == 15_000
    window.shutdown()
    assert window._reconnect_timer.isActive() is False
