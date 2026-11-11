"""Paper execution, accounting, and the Nautilus mapping proof."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from config.settings import Settings
from domain.enums import ExecutionMode
from domain.exceptions import TradingDisabled, TradingValidationError
from domain.shield import PAPER_APPROVED, ExitKind, RiskIntent
from domain.trading import (
    ExecutionReport,
    OrderSide,
    OrderState,
    SimulationOutcome,
    SolanaInstrument,
)
from integrations.gmgn.models import Candle
from integrations.solana.adapter import adapt_gmgn_candle, adapt_observation
from trading.execution.gateway import (
    PaperExecutionGateway,
    PaperOrderRequest,
    refuse_live_execution,
)
from trading.execution.order_manager import ensure_paper_state
from trading.execution.reconciliation import reconcile_position
from trading.memory_store import MemoryTradingStore
from trading.nautilus.data import bar, quote_tick, trade_tick
from trading.nautilus.mapping import NAUTILUS_VERSION, project_instrument
from trading.nautilus.proof import installed_version, run_proof_orders
from trading.portfolio.accounting import apply_fill, unrealized_pnl
from trading.strategies.manager import StrategyManager

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
NOW = datetime(2026, 11, 11, tzinfo=UTC)


def _clock() -> datetime:
    return NOW


def _instrument(price_decimals: int = 6) -> SolanaInstrument:
    return SolanaInstrument(USDC, "USDC", 6, price_decimals, "SOL", 9)


def _request(
    key: str = "paper-order-1",
    *,
    side: OrderSide = OrderSide.BUY,
    quantity: str = "4",
    price: str = "2",
    outcome: SimulationOutcome = SimulationOutcome.FILL,
    fill_quantity: str | None = None,
    fee: str = "0",
    slippage: str = "0",
    shield: bool = False,
    price_decimals: int = 6,
) -> PaperOrderRequest:
    return PaperOrderRequest(
        strategy_id="core-slot",
        instrument=_instrument(price_decimals),
        side=side,
        quantity=Decimal(quantity),
        reference_price=Decimal(price),
        outcome=outcome,
        idempotency_key=key,
        fill_quantity=None if fill_quantity is None else Decimal(fill_quantity),
        fee_quote=Decimal(fee),
        slippage_quote=Decimal(slippage),
        shield_approved=shield,
        risk=None if shield else _risk(side, quantity, price, fee, slippage, price_decimals),
    )


def _risk(
    side: OrderSide,
    quantity: str,
    price: str,
    fee: str,
    slippage: str,
    price_decimals: int,
) -> RiskIntent:
    kind = ExitKind.ENTRY.value if side is OrderSide.BUY else ExitKind.NORMAL.value
    stop = None if side is OrderSide.SELL else Decimal(price) / Decimal(2)
    return RiskIntent(
        mint=USDC,
        side=side.value,
        quantity=Decimal(quantity),
        reference_price=Decimal(price),
        fee_quote=Decimal(fee),
        slippage_quote=Decimal(slippage),
        size_decimals=6,
        price_decimals=price_decimals,
        quote_decimals=9,
        quote_symbol="SOL",
        stop_price=stop,
        equity_quote=None if side is OrderSide.SELL else Decimal(10000),
        sol_balance=None if side is OrderSide.SELL else Decimal(10000),
        valued_at=None if side is OrderSide.SELL else NOW,
        marks=(),
        liquidity_quote=None if side is OrderSide.SELL else Decimal(100000),
        volatility=None,
        confidence=None,
        token_age_seconds=None,
        market_condition=None,
        security=None if side is OrderSide.SELL else "clear",
        creator=None if side is OrderSide.SELL else "DeskWallet",
        narrative=None if side is OrderSide.SELL else "momentum",
        liquidity_provider=None,
        driver=None,
        estimated_impact=None,
        exit_kind=kind,
        signal_ref=None,
        emergency=None,
    )


def _stack(
    mode: ExecutionMode = ExecutionMode.PAPER,
) -> tuple[MemoryTradingStore, PaperExecutionGateway, StrategyManager]:
    store = MemoryTradingStore()
    gateway = PaperExecutionGateway(mode, store, _clock)
    manager = StrategyManager(mode, store, gateway, _clock)
    return store, gateway, manager


def test_read_only_stores_nothing() -> None:
    store, gateway, _manager = _stack(ExecutionMode.READ_ONLY)
    with pytest.raises(TradingDisabled, match="Read-only"):
        gateway.submit(_request())
    assert store.orders == {}
    assert store.positions == {}


def test_live_entry_refuses_without_a_payload() -> None:
    with pytest.raises(TradingDisabled, match="No wallet"):
        refuse_live_execution("swap")
    with pytest.raises(TradingDisabled, match="unknown"):
        refuse_live_execution("../swap?key=secret")


def test_paper_states_cannot_mean_a_submission() -> None:
    for state in (
        OrderState.SUBMISSION_PENDING,
        OrderState.SUBMITTED,
        OrderState.CONFIRMATION_PENDING,
    ):
        with pytest.raises(TradingDisabled):
            ensure_paper_state(state)


def test_buy_fee_changes_average_and_a_repeat_key_does_not() -> None:
    store, gateway, _manager = _stack()
    first = gateway.submit(_request(fee="1"))
    assert first.state is OrderState.CONFIRMED
    assert first.shield_decision == PAPER_APPROVED
    assert first.simulated is True
    position = store.positions[USDC]
    assert position.quantity == Decimal(4)
    assert position.average_price == Decimal("2.25")
    assert position.cost_quote == Decimal(9)
    second = gateway.submit(_request(quantity="99", fee="5"))
    assert second.client_order_id == first.client_order_id
    assert store.positions[USDC].quantity == Decimal(4)
    notes = [note for _state, note in store.events[first.client_order_id]]
    assert any(note.startswith("TradeIntentCreated") for note in notes)
    assert any(note.startswith("ExecutionConfirmed") for note in notes)
    assert OrderState.SUBMITTED.value not in {
        state for state, _note in store.events[first.client_order_id]
    }


def test_partial_sell_realizes_result_and_oversell_fails() -> None:
    store, gateway, _manager = _stack()
    gateway.submit(_request(quantity="10", price="2", fee="1"))
    sold = gateway.submit(
        _request(
            "paper-sell-1",
            side=OrderSide.SELL,
            quantity="10",
            price="3",
            outcome=SimulationOutcome.PARTIAL,
            fill_quantity="4",
            fee="0.5",
        )
    )
    assert sold.filled_quantity == Decimal(4)
    assert sold.state is OrderState.CONFIRMED
    position = store.positions[USDC]
    assert position.quantity == Decimal(6)
    assert position.average_price == Decimal("2.1")
    assert position.realized_pnl_quote == Decimal("3.1")
    failed = gateway.submit(_request("paper-sell-2", side=OrderSide.SELL, quantity="7", price="3"))
    assert failed.state is OrderState.FAILED
    assert failed.reason == "insufficient_position"
    assert store.positions[USDC].quantity == Decimal(6)
    assert unrealized_pnl(store.positions[USDC], None) is None
    assert unrealized_pnl(store.positions[USDC], Decimal("3")) == Decimal("5.4")


def test_reject_and_explicit_failure_do_not_change_a_position() -> None:
    store, gateway, _manager = _stack()
    rejected = gateway.submit(_request(outcome=SimulationOutcome.REJECT))
    failed = gateway.submit(_request("paper-fail-1", outcome=SimulationOutcome.FAIL))
    assert rejected.state is OrderState.FAILED
    assert rejected.reason == "rejected"
    assert failed.reason == "simulated_failure"
    assert store.positions == {}


def test_slippage_is_applied_only_as_supplied() -> None:
    store, gateway, _manager = _stack()
    order = gateway.submit(_request(price="2", slippage="0.25"))
    assert order.fill_price == Decimal("2.25")
    assert store.positions[USDC].average_price == Decimal("2.25")


def test_strategy_cannot_approve_or_submit_while_stopped() -> None:
    store, _gateway, manager = _stack()
    manager.register("core-slot", "Core slot")
    with pytest.raises(TradingDisabled, match="stopped"):
        manager.submit("core-slot", _request())
    started = manager.start("core-slot")
    assert started.state.value == "RUNNING"
    with pytest.raises(TradingDisabled, match="cannot approve"):
        manager.submit("core-slot", _request("paper-approved", shield=True))
    order = manager.submit("core-slot", _request())
    assert order.shield_decision == PAPER_APPROVED
    assert manager.stop_running() == 1
    assert store.get_strategy("core-slot").state.value == "STOPPED"  # type: ignore[union-attr]


def test_read_only_cannot_start_a_strategy() -> None:
    _store, _gateway, manager = _stack(ExecutionMode.READ_ONLY)
    manager.register("core-slot", "Core slot")
    with pytest.raises(TradingDisabled):
        manager.start("core-slot")


def test_secret_parameter_names_are_rejected() -> None:
    _store, _gateway, manager = _stack()
    with pytest.raises(TradingValidationError, match="secret"):
        manager.register("core-slot", "Core slot", {"api_key": "not-stored"})


def test_reconciliation_does_not_retry_or_rewrite_the_position() -> None:
    store, gateway, _manager = _stack()
    order = gateway.submit(_request())
    matched = gateway.reconcile(
        order.client_order_id,
        ExecutionReport(
            order.client_order_id, order.state, order.filled_quantity, order.fill_price
        ),
    )
    assert matched.status.value == "MATCHED"
    assert store.positions[USDC].quantity == Decimal(4)
    unknown = gateway.reconcile(order.client_order_id, None)
    assert unknown.status.value == "UNKNOWN"
    assert store.get_order(order.client_order_id).state is OrderState.UNKNOWN  # type: ignore[union-attr]
    assert store.positions[USDC].quantity == Decimal(4)
    conflict = gateway.reconcile(
        order.client_order_id,
        ExecutionReport(order.client_order_id, OrderState.CONFIRMED, Decimal(1), Decimal(2)),
    )
    assert conflict.status.value == "CONFLICT"
    assert "not retried" in conflict.detail
    assert store.positions[USDC].quantity == Decimal(4)
    assert reconcile_position(Decimal(4), Decimal(4)).value == "MATCHED"
    assert reconcile_position(Decimal(4), Decimal(3)).value == "CONFLICT"


def test_gmgn_candle_does_not_invent_a_book() -> None:
    candle = Candle(
        time=1_700_000_000,
        open=Decimal("1"),
        high=Decimal("1.2"),
        low=Decimal("0.9"),
        close=Decimal("1.1"),
        volume=Decimal("10"),
    )
    quote = adapt_gmgn_candle(USDC, candle, NOW)
    assert quote.last_price == Decimal("1.1")
    assert quote.bid is None
    assert quote.ask is None
    assert quote.size_is_base is False
    assert quote.volume == Decimal(10)
    assert bar(_instrument(), quote) is None
    with pytest.raises(TradingValidationError):
        adapt_observation("not-a-mint", NOW, source="supplied")


def test_nautilus_data_requires_real_fields_and_nine_decimals() -> None:
    assert installed_version() == NAUTILUS_VERSION
    wide = _instrument(price_decimals=12)
    projection, pair = project_instrument(wide)
    assert projection.representable is False
    assert projection.reason == "nautilus_fixed_precision_9"
    assert pair is None
    instrument = _instrument()
    bare = adapt_observation(USDC, NOW, source="supplied", last_price=Decimal("1"))
    assert quote_tick(instrument, bare) is None
    assert trade_tick(instrument, bare) is None
    quoted = adapt_observation(
        USDC,
        NOW,
        source="supplied",
        bid=Decimal("1.00"),
        ask=Decimal("1.01"),
        bid_size=Decimal("2"),
        ask_size=Decimal("3"),
        last_price=Decimal("1.01"),
        last_size=Decimal("3"),
        open_price=Decimal("1"),
        high=Decimal("1.2"),
        low=Decimal("0.9"),
        close=Decimal("1.1"),
        size_is_base=True,
        bar_resolution="1m",
    )
    assert quote_tick(instrument, quoted) is not None
    assert trade_tick(instrument, quoted) is not None
    assert bar(instrument, quoted) is not None
    represented, nautilus_pair = project_instrument(instrument)
    assert represented.representable is True
    assert represented.instrument_id is not None
    assert represented.instrument_id.endswith(".SOLANA")
    assert nautilus_pair is not None


def test_nautilus_proof_fills_partially_and_denies_without_cash() -> None:
    results = {item.label: item for item in run_proof_orders()}
    assert results["full"].status == "FILLED"
    assert results["full"].filled == "10.000000"
    assert results["full"].events.count("OrderFilled") == 1
    assert "OrderSubmitted" in results["partial"].events
    assert results["partial"].status == "CANCELED"
    assert results["partial"].filled == "5.000000"
    assert "OrderCanceled" in results["partial"].events
    assert results["denied"].status == "DENIED"
    assert results["denied"].filled == "0.000000"
    assert "OrderDenied" in results["denied"].events


def test_trading_routes_require_a_token_and_stay_simulated(tmp_path) -> None:  # type: ignore[no-untyped-def]
    secret = "local-test-token"
    settings = Settings(
        _env_file=None,
        log_dir=tmp_path,
        api_token=secret,
        execution_mode=ExecutionMode.PAPER,
    )
    app = create_app(settings)
    store = MemoryTradingStore()
    app.state.trading_store = store
    app.state.trading_clock = _clock
    client = TestClient(app)
    assert client.get("/trading/orders").status_code == 401
    headers = {"Authorization": f"Bearer {secret}"}
    status = client.get("/trading/status", headers=headers)
    assert status.status_code == 200
    body = status.json()
    assert body["live_trading_enabled"] is False
    assert body["paper_orders_enabled"] is True
    assert body["shield_decision"] == "enforcing"
    assert body["nautilus_version"] == NAUTILUS_VERSION
    refused = client.post("/trading/live/swap", headers=headers)
    assert refused.status_code == 403
    assert "secret" not in refused.text
    registered = client.post(
        "/trading/strategies",
        headers=headers,
        json={"strategy_id": "core-slot", "name": "Core slot"},
    )
    assert registered.status_code == 200
    assert client.post("/trading/strategies/core-slot/start", headers=headers).status_code == 200
    created = client.post(
        "/trading/paper/orders",
        headers=headers,
        json={
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
            "idempotency_key": "route-order-1",
        },
    )
    assert created.status_code == 200
    denied = created.json()
    assert denied["state"] == "FAILED"
    assert denied["reason"] == "valuation_unverified"
    assert denied["shield_decision"] == "denied"
    assert denied["simulated"] is True
    assert USDC not in store.positions
    approved = client.post(
        "/trading/paper/orders",
        headers=headers,
        json={
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
            "idempotency_key": "route-order-approved",
            "stop_price": "1",
            "equity_quote": "10000",
            "sol_balance": "10000",
            "valued_at": "2026-11-11T00:00:00+00:00",
            "liquidity_quote": "100000",
            "security": "clear",
            "creator": "DeskWallet",
            "narrative": "momentum",
        },
    )
    assert approved.status_code == 200
    payload = approved.json()
    assert payload["state"] == "CONFIRMED"
    assert payload["simulated"] is True
    assert payload["shield_decision"] == "paper_approved"
    assert store.positions[USDC].quantity == Decimal(2)
    positions = client.get("/trading/positions", headers=headers)
    assert positions.json()[0]["quantity"] == "2"
    blocked = client.post(
        "/trading/paper/orders",
        headers=headers,
        json={
            "strategy_id": "core-slot",
            "mint": USDC,
            "symbol": "USDC",
            "side": "BUY",
            "quantity": "1",
            "reference_price": "1",
            "quote_symbol": "SOL",
            "size_decimals": 6,
            "price_decimals": 6,
            "quote_decimals": 9,
            "idempotency_key": "route-order-2",
            "shield_approved": True,
        },
    )
    assert blocked.status_code == 403
    assert store.positions[USDC].quantity == Decimal(2)


def test_trading_source_has_no_signer_or_gmgn_trade_call() -> None:
    root = Path(__file__).resolve().parents[2]
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for directory in (root / "trading", root / "integrations" / "solana", root / "shield")
        for path in directory.rglob("*.py")
    )
    assert "GMGN_PRIVATE_KEY" not in text
    assert "/v1/trade/" not in text
    assert "LiveExecutionClient" not in text
    assert "Keypair" not in text
    assert "solders" not in text
    assert "GMGNExecutionGateway" not in text


def test_buy_then_flat_average_uses_decimal_cost() -> None:
    position = apply_fill(
        None,
        mint=USDC,
        side=OrderSide.BUY,
        filled_quantity=Decimal(10),
        fill_price=Decimal(2),
        fee_quote=Decimal(1),
        quote_symbol="SOL",
        now=NOW,
    )
    flat = apply_fill(
        position,
        mint=USDC,
        side=OrderSide.SELL,
        filled_quantity=Decimal(10),
        fill_price=Decimal(3),
        fee_quote=Decimal("0.5"),
        quote_symbol="SOL",
        now=NOW,
    )
    assert flat.quantity == Decimal(0)
    assert flat.average_price is None
    assert flat.realized_pnl_quote == Decimal("8.5")
    assert unrealized_pnl(flat, None) == Decimal(0)
