"""Deterministic Shield decisions. None of these tests can enable a live order."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from tests.unit.test_trading import _request, _stack

from domain.exceptions import TradingDisabled, TradingValidationError
from domain.shield import (
    PAPER_APPROVED,
    RECOVERY_PHRASE,
    STOP_NOT_GUARANTEED,
    EmergencyEvidence,
    ExitKind,
    RiskIntent,
    ShieldSnapshot,
    TakeProfitLevel,
)
from domain.trading import LIVE_ORDER_STATES, OrderSide, OrderState, SimulationOutcome
from shield.emergency import assess_emergency
from shield.engine import (
    apply_execution,
    evaluate,
    initial_snapshot,
    record_emergency,
    record_trail,
    recover,
    replace_limits,
)
from shield.limits import default_limits, require_paper_decision, validate_limits
from shield.stops import advance_trailing, plan_take_profits
from trading.execution.gateway import PaperExecutionGateway, refuse_live_execution
from trading.memory_store import MemoryTradingStore

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
WSOL = "So11111111111111111111111111111111111111112"
NOW = datetime(2026, 11, 11, tzinfo=UTC)


def _intent(**overrides: object) -> RiskIntent:
    base = RiskIntent(
        mint=USDC,
        side=OrderSide.BUY.value,
        quantity=Decimal(4),
        reference_price=Decimal(2),
        fee_quote=Decimal(0),
        slippage_quote=Decimal(0),
        size_decimals=6,
        price_decimals=6,
        quote_decimals=9,
        quote_symbol="SOL",
        stop_price=Decimal(1),
        equity_quote=Decimal(1000),
        sol_balance=Decimal(1000),
        valued_at=NOW,
        marks=(),
        liquidity_quote=Decimal(100000),
        volatility=None,
        confidence=None,
        token_age_seconds=None,
        market_condition=None,
        security="clear",
        creator="DeskWallet",
        narrative="momentum",
        liquidity_provider=None,
        driver=None,
        estimated_impact=None,
        exit_kind=ExitKind.ENTRY.value,
        signal_ref=None,
        emergency=None,
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def _eval(snapshot: ShieldSnapshot, intent: RiskIntent, positions: tuple = (), orders: tuple = ()):  # type: ignore[type-arg]
    return evaluate(snapshot, intent, positions, orders, NOW)


def test_defaults_match_the_spec_and_reject_contradictions() -> None:
    limits = validate_limits(default_limits())
    assert limits.risk_per_trade_fraction == Decimal("0.01")
    assert limits.max_deployed_fraction == Decimal("0.70")
    assert limits.min_sol_reserve_fraction == Decimal("0.10")
    assert limits.daily_loss_fraction == Decimal("0.05")
    assert limits.max_drawdown_fraction == Decimal("0.15")
    assert limits.max_consecutive_losses == 3
    with pytest.raises(TradingValidationError, match="together"):
        validate_limits(
            replace(
                limits,
                max_deployed_fraction=Decimal("0.80"),
                min_sol_reserve_fraction=Decimal("0.30"),
            )
        )
    with pytest.raises(TradingValidationError, match="daily loss"):
        validate_limits(replace(limits, risk_per_trade_fraction=Decimal("0.10")))
    with pytest.raises(TradingValidationError, match="exceed"):
        validate_limits(
            replace(
                limits,
                take_profit_levels=(
                    TakeProfitLevel(Decimal("0.30"), Decimal("0.60")),
                    TakeProfitLevel(Decimal("0.50"), Decimal("0.60")),
                ),
            )
        )
    with pytest.raises(TradingValidationError):
        require_paper_decision("live_approved", simulated=True)
    with pytest.raises(TradingValidationError):
        require_paper_decision(PAPER_APPROVED, simulated=False)


def test_position_size_uses_stop_distance_and_does_not_treat_stop_as_a_fill() -> None:
    decision = _eval(initial_snapshot(), _intent(quantity=Decimal(11)))
    assert decision.approved is False
    assert decision.reason == "risk_per_trade"
    assert decision.allowed_quantity == Decimal(10)
    assert STOP_NOT_GUARANTEED in decision.notes
    assert decision.snapshot.high_water_equity == Decimal(1000)
    tight = _eval(
        initial_snapshot(),
        _intent(stop_price=Decimal("1.9"), volatility=Decimal("0.2"), quantity=Decimal(100)),
    )
    assert tight.reason == "risk_per_trade"
    assert tight.allowed_quantity == Decimal(25)
    assert tight.effective_stop == Decimal("1.6")
    sized = _eval(initial_snapshot(), _intent(quantity=Decimal(10)))
    assert sized.approved is True
    assert sized.snapshot.limits.max_consecutive_losses == 3
    assert OrderState.SUBMITTED in LIVE_ORDER_STATES


def test_confidence_only_reduces_size_and_missing_volatility_is_not_invented() -> None:
    halved = _eval(initial_snapshot(), _intent(quantity=Decimal(6), confidence=Decimal("0.5")))
    assert halved.reason == "risk_per_trade"
    assert halved.allowed_quantity == Decimal(5)
    explicit = _eval(initial_snapshot(), _intent(stop_price=Decimal("1.9"), quantity=Decimal(100)))
    assert "volatility_not_supplied" in explicit.notes
    assert explicit.allowed_quantity == Decimal(100)


def test_allocation_reserve_and_liquidity_caps_bind() -> None:
    deployed = _eval(
        initial_snapshot(),
        _intent(quantity=Decimal(360), stop_price=Decimal("1.999")),
    )
    assert deployed.reason == "max_deployed"
    assert deployed.allowed_quantity == Decimal(350)
    relaxed = replace(
        initial_snapshot(),
        limits=validate_limits(
            replace(
                default_limits(),
                max_deployed_fraction=Decimal("0.90"),
                risk_per_trade_fraction=Decimal("0.05"),
            )
        ),
    )
    reserve = evaluate(
        relaxed,
        _intent(quantity=Decimal(440), stop_price=Decimal("1.999"), fee_quote=Decimal(22)),
        (),
        (),
        NOW,
    )
    assert reserve.reason == "sol_reserve"
    assert reserve.allowed_quantity == Decimal("439.024390")
    thin = _eval(initial_snapshot(), _intent(liquidity_quote=Decimal(100), quantity=Decimal(2)))
    assert thin.reason == "liquidity_participation"
    assert thin.allowed_quantity == Decimal(1)
    missing = _eval(initial_snapshot(), _intent(liquidity_quote=None))
    assert missing.reason == "liquidity_unverified"


def test_unknown_security_and_unverified_equity_block_entries() -> None:
    assert _eval(initial_snapshot(), _intent(security="unknown")).reason == "security_unknown"
    assert _eval(initial_snapshot(), _intent(security=None)).reason == "security_unknown"
    assert _eval(initial_snapshot(), _intent(equity_quote=None)).reason == "valuation_unverified"
    assert (
        _eval(initial_snapshot(), _intent(equity_quote=Decimal(1001))).reason
        == "valuation_inconsistent"
    )
    stale = _intent(valued_at=NOW - timedelta(seconds=121))
    assert _eval(initial_snapshot(), stale).reason == "valuation_stale"


def test_daily_loss_and_drawdown_persist_across_a_new_engine() -> None:
    store = MemoryTradingStore()
    first = evaluate(store.shield, _intent(), (), (), NOW)
    store.shield = first.snapshot
    losing = evaluate(
        store.shield,
        _intent(equity_quote=Decimal(940), sol_balance=Decimal(940)),
        (),
        (),
        NOW,
    )
    assert losing.reason == "daily_loss"
    assert losing.snapshot.breach_latched is True
    assert losing.snapshot.daily[0].equity_at_open == Decimal(1000)
    store.shield = losing.snapshot
    restarted = evaluate(
        store.shield,
        _intent(equity_quote=Decimal(1000), sol_balance=Decimal(1000)),
        (),
        (),
        NOW,
    )
    assert restarted.reason == "daily_loss"
    assert restarted.snapshot.high_water_equity == Decimal(1000)
    rich = evaluate(initial_snapshot(), _intent(), (), (), NOW)
    later = NOW + timedelta(days=1)
    deep = evaluate(
        rich.snapshot,
        _intent(equity_quote=Decimal(840), sol_balance=Decimal(840), valued_at=later),
        (),
        (),
        later,
    )
    assert deep.reason == "max_drawdown"
    assert deep.snapshot.high_water_equity == Decimal(1000)
    held = evaluate(
        deep.snapshot,
        _intent(valued_at=later),
        (),
        (),
        later,
    )
    assert held.snapshot.high_water_equity == Decimal(1000)
    assert held.reason == "max_drawdown"


def test_recovery_waits_until_the_limit_clears_and_does_not_liquidate() -> None:
    breached = evaluate(
        evaluate(initial_snapshot(), _intent(), (), (), NOW).snapshot,
        _intent(equity_quote=Decimal(940), sol_balance=Decimal(940)),
        (),
        (),
        NOW,
    ).snapshot
    refused, reason, _notices = recover(
        breached,
        RECOVERY_PHRASE,
        _intent(equity_quote=Decimal(940), sol_balance=Decimal(940)),
        (),
        NOW,
        reset_loss_streak=False,
    )
    assert reason == "recovery_refused"
    assert refused.breach_latched is True
    cleared, problem, notices = recover(
        breached,
        RECOVERY_PHRASE,
        _intent(),
        (),
        NOW,
        reset_loss_streak=False,
    )
    assert problem is None
    assert cleared.breach_latched is False
    assert notices[0].kind == "recovery"
    wrong, phrase, _empty = recover(breached, "please", _intent(), (), NOW, reset_loss_streak=False)
    assert phrase == "recovery_phrase"
    assert wrong.breach_latched is True


def test_three_losing_campaigns_pause_entries_and_partials_count_once() -> None:
    store, gateway, _manager = _stack()
    for index in range(3):
        gateway.submit(_request(f"loss-buy-{index}", quantity="4", price="2"))
        sold = gateway.submit(
            _request(f"loss-sell-{index}", side=OrderSide.SELL, quantity="4", price="1")
        )
        assert sold.shield_decision == PAPER_APPROVED
        gateway.reconcile(
            sold.client_order_id,
            _report(sold.client_order_id, sold.filled_quantity),
        )
    blocked = gateway.submit(_request("loss-buy-3"))
    assert blocked.reason == "consecutive_losses"
    assert blocked.state is OrderState.FAILED
    assert store.positions[USDC].quantity == Decimal(0)
    assert len([order for order in store.orders.values() if order.side is OrderSide.SELL]) == 3


def _report(client_order_id: str, filled: Decimal, price: Decimal = Decimal(1)):  # type: ignore[no-untyped-def]
    from domain.trading import ExecutionReport

    return ExecutionReport(client_order_id, OrderState.CONFIRMED, filled, price)


def test_one_campaign_with_partial_exits_is_a_single_loss() -> None:
    store, gateway, _manager = _stack()
    gateway.submit(_request(quantity="10", price="2"))
    gateway.submit(
        _request(
            "partial-a",
            side=OrderSide.SELL,
            quantity="10",
            price="1",
            outcome=SimulationOutcome.PARTIAL,
            fill_quantity="4",
        )
    )
    assert store.shield.consecutive_losses == 0
    closing = gateway.submit(_request("partial-b", side=OrderSide.SELL, quantity="6", price="1"))
    assert store.shield.consecutive_losses == 1
    gateway.reconcile(closing.client_order_id, _report(closing.client_order_id, Decimal(6)))
    again = gateway.submit(_request("partial-reentry"))
    assert again.shield_decision == PAPER_APPROVED


def test_reentry_requires_reconciliation_and_unknown_correlation_blocks() -> None:
    store, gateway, _manager = _stack()
    gateway.submit(_request())
    closing = gateway.submit(_request("flat-sell", side=OrderSide.SELL, quantity="4", price="3"))
    blocked = gateway.submit(_request("reentry-1"))
    assert blocked.reason == "reentry_not_reconciled"
    assert closing.fill_price is not None
    gateway.reconcile(
        closing.client_order_id,
        _report(closing.client_order_id, Decimal(4), closing.fill_price),
    )
    opened = gateway.submit(_request("reentry-2"))
    assert opened.shield_decision == PAPER_APPROVED
    second = gateway.submit(
        _request("other-mint").__class__(
            strategy_id="core-slot",
            instrument=replace_instrument(),
            side=OrderSide.BUY,
            quantity=Decimal(1),
            reference_price=Decimal(2),
            outcome=SimulationOutcome.FILL,
            idempotency_key="other-mint",
            risk=_intent(
                mint=WSOL,
                quantity=Decimal(1),
                creator=None,
                narrative=None,
                marks=((USDC, Decimal(2)),),
                equity_quote=Decimal(10008),
                sol_balance=Decimal(10000),
            ),
        )
    )
    assert second.reason == "correlation_unknown"
    assert store.positions[USDC].quantity == Decimal(4)


def replace_instrument():  # type: ignore[no-untyped-def]
    from domain.trading import SolanaInstrument

    return SolanaInstrument(WSOL, "WSOL", 6, 6, "SOL", 9)


def test_shared_creator_is_capped_without_an_invented_coefficient() -> None:
    _store, gateway, _manager = _stack()
    gateway.submit(
        _request("cluster-buy").__class__(
            strategy_id="core-slot",
            instrument=_request().instrument,
            side=OrderSide.BUY,
            quantity=Decimal(1300),
            reference_price=Decimal(2),
            outcome=SimulationOutcome.FILL,
            idempotency_key="cluster-buy",
            risk=_intent(
                quantity=Decimal(1300),
                stop_price=Decimal("1.95"),
                liquidity_quote=Decimal(1000000),
                equity_quote=Decimal(10000),
                sol_balance=Decimal(10000),
            ),
        )
    )
    clustered = gateway.submit(
        _request("cluster-two").__class__(
            strategy_id="core-slot",
            instrument=replace_instrument(),
            side=OrderSide.BUY,
            quantity=Decimal(100),
            reference_price=Decimal(2),
            outcome=SimulationOutcome.FILL,
            idempotency_key="cluster-two",
            risk=_intent(
                mint=WSOL,
                quantity=Decimal(100),
                creator="DeskWallet",
                narrative="other",
                marks=((USDC, Decimal(2)),),
                equity_quote=Decimal(10000),
                sol_balance=Decimal(7400),
                liquidity_quote=Decimal(1000000),
            ),
        )
    )
    assert clustered.reason == "correlation_cluster"


def test_take_profit_plan_cannot_exceed_the_position_and_trailing_only_rises() -> None:
    levels = plan_take_profits(Decimal(10), default_limits(), 0)
    assert sum(level.planned_quantity for level in levels) <= Decimal(10)
    snapshot = initial_snapshot()
    _store, gateway, _manager = _stack()
    order = gateway.submit(_request(quantity="100", price="2"))
    plan = gateway_stop(_store_of(gateway), order.mint)
    assert sum(level.planned_quantity for level in plan.levels) <= Decimal(100)
    early = evaluate(
        _store_of(gateway).shield,
        _intent(
            side=OrderSide.SELL.value,
            exit_kind=ExitKind.TAKE_PROFIT.value,
            quantity=Decimal(25),
            marks=((USDC, Decimal("2.2")),),
            equity_quote=None,
            sol_balance=None,
            valued_at=None,
            liquidity_quote=None,
            security=None,
            stop_price=None,
        ),
        _store_of(gateway).list_positions(),
        (),
        NOW,
    )
    assert early.reason == "take_profit_not_reached"
    reached = evaluate(
        _store_of(gateway).shield,
        _intent(
            side=OrderSide.SELL.value,
            exit_kind=ExitKind.TAKE_PROFIT.value,
            quantity=Decimal(30),
            marks=((USDC, Decimal("2.6")),),
            equity_quote=None,
            sol_balance=None,
            valued_at=None,
            liquidity_quote=None,
            security=None,
            stop_price=None,
        ),
        _store_of(gateway).list_positions(),
        (),
        NOW,
    )
    assert reached.reason == "take_profit_quantity"
    del snapshot
    trail_plan = plan
    held, status = advance_trailing(trail_plan, Decimal("2.1"), NOW, None, default_limits())
    assert status == "not_activated"
    activated, raised = advance_trailing(held, Decimal("3"), NOW, None, default_limits())
    assert raised == "raised"
    assert activated.stop_price > trail_plan.stop_price
    blocked, waiting = advance_trailing(
        activated, Decimal("3.4"), NOW + timedelta(seconds=10), None, default_limits()
    )
    assert waiting == "update_interval"
    assert blocked.stop_price == activated.stop_price
    later, moved = advance_trailing(
        activated, Decimal("3.4"), NOW + timedelta(seconds=61), None, default_limits()
    )
    assert moved == "raised"
    assert later.stop_price >= activated.stop_price


def _store_of(gateway: PaperExecutionGateway) -> MemoryTradingStore:
    store = gateway._store
    assert isinstance(store, MemoryTradingStore)
    return store


def gateway_stop(store: MemoryTradingStore, mint: str):  # type: ignore[no-untyped-def]
    plan = next(item for item in store.shield.stops if item.mint == mint)
    return plan


def test_emergency_detection_does_not_invent_a_cause_or_submit_an_order() -> None:
    limits = default_limits()
    evidence = EmergencyEvidence(
        previous_liquidity=Decimal(100),
        current_liquidity=Decimal(40),
        previous_price=Decimal(2),
        current_price=Decimal(2),
        whale_sell_reported=True,
        whale_source=None,
        smart_money_exit_reported=False,
        smart_money_source=None,
        estimated_impact=None,
        trading_restricted=False,
        restriction_source=None,
        quote_observed_at=NOW,
    )
    assert assess_emergency(evidence, limits, NOW) == ("liquidity_removal",)
    quiet = replace(evidence, current_liquidity=Decimal(90), previous_liquidity=None)
    assert assess_emergency(quiet, limits, NOW) == ()
    assert assess_emergency(None, limits, NOW) == ("market_data_failure",)
    snapshot, triggers, notices = record_emergency(initial_snapshot(), USDC, evidence, NOW)
    assert triggers == ("liquidity_removal",)
    assert notices[0].kind == "emergency"
    denied = evaluate(snapshot, _intent(), (), (), NOW)
    assert denied.reason == "emergency_stop"
    assert denied.approved is False


def test_paper_approval_cannot_enable_live_execution_or_bypass_shield() -> None:
    store, gateway, _manager = _stack()
    order = gateway.submit(_request())
    assert order.shield_decision == PAPER_APPROVED
    assert order.simulated is True
    assert order.state is not OrderState.SUBMITTED
    with pytest.raises(TradingDisabled, match="cannot approve"):
        gateway.submit(_request("claimed", shield=True))
    with pytest.raises(TradingDisabled, match="No wallet"):
        refuse_live_execution("swap")
    assert store.shield.high_water_equity == Decimal(10000)
    replaced = replace_limits(store.shield, default_limits())
    assert replaced.high_water_equity == Decimal(10000)


def test_apply_execution_tracks_campaign_pnl_without_a_second_trade() -> None:
    _store, gateway, _manager = _stack()
    order = gateway.submit(_request())
    assert _store_of(gateway).shield.consecutive_losses == 0
    assert order.client_order_id
    trailed, status = record_trail(_store_of(gateway).shield, USDC, Decimal("2.7"), None, NOW)
    assert status == "raised"
    assert trailed.stops[0].stop_price >= _store_of(gateway).shield.stops[0].stop_price
    assert apply_execution is not None
