"""Paper Nautilus health check and the operator book views."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import create_app
from config.settings import Settings
from domain.enums import ExecutionMode
from domain.status import StatusSnapshot
from terminal.assemble import assemble
from terminal.profiles import default_preferences, default_profile
from trading.memory_store import MemoryTradingStore
from trading.nautilus.health import run_nautilus_health
from trading.nautilus.mapping import NAUTILUS_VERSION

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
NOW = datetime(2026, 11, 11, tzinfo=UTC)


def test_nautilus_health_runs_the_paper_core() -> None:
    report = run_nautilus_health()
    assert report.version == NAUTILUS_VERSION
    assert report.passed, {item.name: item.detail for item in report.checks}
    names = [item.name for item in report.checks]
    assert names == [
        "import",
        "backtest_node",
        "instrument_fill",
        "shield_paper_book",
        "kill_switch",
        "stored_backtest",
    ]


def test_paper_order_reaches_api_and_terminal_views(tmp_path: Path, monkeypatch: object) -> None:
    secret = "local-health-token"
    settings = Settings(
        _env_file=None,
        log_dir=tmp_path,
        api_token=secret,
        execution_mode=ExecutionMode.PAPER,
    )
    app = create_app(settings)
    store = MemoryTradingStore()
    app.state.trading_store = store
    app.state.trading_clock = lambda: NOW
    app.state.terminal_repository = _BookTerminal(store)
    app.state.terminal_clock = lambda: NOW
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {secret}"}
    client.post(
        "/trading/strategies",
        headers=headers,
        json={"strategy_id": "core-slot", "name": "Core slot"},
    )
    client.post("/trading/strategies/core-slot/start", headers=headers)
    created = client.post(
        "/trading/paper/orders",
        headers=headers,
        json=_order("route-health-1"),
    )
    assert created.status_code == 200
    body = created.json()
    assert body["state"] == "CONFIRMED"
    assert body["shield_decision"] == "paper_approved"
    assert body["simulated"] is True
    positions = client.get("/trading/positions", headers=headers)
    assert positions.status_code == 200
    assert positions.json()[0]["quantity"] == "2"
    assert positions.json()[0]["realized_pnl_quote"] == "0"
    snapshot = client.get("/terminal/snapshot", headers=headers)
    assert snapshot.status_code == 200
    view = snapshot.json()
    assert view["live_trading_enabled"] is False
    assert view["authorizes_order"] is False
    assert view["portfolio"]["open_positions"] == 1

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "apps.api.routes.trading.operator_orders_blocked",
        lambda _settings: True,
    )
    blocked = client.post(
        "/trading/paper/orders",
        headers=headers,
        json=_order("route-health-2"),
    )
    assert blocked.status_code == 403
    assert "kill switch" in blocked.text
    assert store.positions[USDC].quantity == Decimal(2)
    replay = client.post(
        "/trading/paper/orders",
        headers=headers,
        json=_order("route-health-1"),
    )
    assert replay.status_code == 200
    assert replay.json()["client_order_id"] == body["client_order_id"]
    assert len(store.orders) == 1


def _order(key: str) -> dict[str, object]:
    return {
        "strategy_id": "core-slot",
        "mint": USDC,
        "symbol": "USDC",
        "side": "BUY",
        "quantity": "2",
        "reference_price": "1.5",
        "quote_symbol": "SOL",
        "size_decimals": 6,
        "price_decimals": 6,
        "quote_decimals": 9,
        "idempotency_key": key,
        "stop_price": "1",
        "equity_quote": "10000",
        "sol_balance": "10000",
        "valued_at": "2026-11-11T00:00:00+00:00",
        "liquidity_quote": "100000",
        "security": "clear",
        "creator": "DeskWallet",
        "narrative": "momentum",
    }


class _BookTerminal:
    def __init__(self, store: MemoryTradingStore) -> None:
        self._store = store

    def load(self, status: object, now: datetime) -> object:
        current = status if isinstance(status, StatusSnapshot) else None
        return assemble(
            trading=self._store.snapshot(),
            shield=self._store.load_shield(),
            notices=self._store.list_notices(),
            decisions=self._store.list_decisions(),
            cycle=None,
            simulation_reports=(),
            profiles=(default_profile(),),
            preferences=default_preferences(),
            existing_notifications=(),
            execution_mode="PAPER",
            database_configured=False,
            gmgn_configured=False,
            api_host="127.0.0.1",
            api_port=8787,
            status=current,
            now=now,
        )

    def save_profile(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("The health view does not save a profile.")

    def activate_profile(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    def save_preferences(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    def pause_entries(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    def resume_entries(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
