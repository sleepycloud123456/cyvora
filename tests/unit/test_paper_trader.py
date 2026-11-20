"""The autonomous paper trader stays inside Shield and the virtual bankroll."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from PySide6.QtWidgets import QLabel

from apps.desktop.pages.dashboard_page import DashboardPage
from config.settings import Settings
from domain.enums import ExecutionMode
from domain.paper_trader import (
    PoolQuote,
    RadarCandidate,
    StoredTraderCycle,
    StoredTraderDecision,
)
from domain.shield import PAPER_APPROVED
from domain.trading import OrderSide, OrderState, StrategyState
from operations.assembly import default_workers
from terminal.paper_trader import build_paper_trader_view
from trading.memory_store import MemoryTradingStore
from trading.paper_trader.candidates import candidate_from_analysis
from trading.paper_trader.loop import run_once
from trading.paper_trader.quotes import collect_marks, stored_mark_max_age_seconds
from trading.paper_trader.runtime import run_stored

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
WSOL = "So11111111111111111111111111111111111111112"
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def test_entry_goes_through_shield_and_a_repeat_does_not_double_fill() -> None:
    store = MemoryTradingStore()
    first = run_once(**_kwargs(store, (_candidate(),), _quotes()))
    assert first.status == "running"
    assert first.submitted_count == 1
    assert first.equity_quote is not None
    assert first.decisions[-1].action == "submitted"
    assert first.decisions[-1].live_trading_enabled is False
    order = store.list_orders()[0]
    assert order.shield_decision == PAPER_APPROVED
    assert order.side is OrderSide.BUY
    assert order.simulated is True
    assert order.strategy_id == "radar-paper"
    assert order.fill_price is not None
    assert order.fill_price != Decimal("0.001")
    assert store.get_strategy("radar-paper") is not None
    assert store.get_strategy("radar-paper").state is StrategyState.STOPPED  # type: ignore[union-attr]
    second = run_once(**_kwargs(store, (_candidate(),), _quotes(), now=NOW + timedelta(minutes=2)))
    assert second.submitted_count == 0
    assert second.decisions[-1].reason == "position_open"
    assert len(store.list_orders()) == 1


def test_ranked_clear_security_can_enter() -> None:
    store = MemoryTradingStore()
    result = run_once(**_kwargs(store, (_candidate(lifecycle="ranked"),), _quotes()))
    assert result.submitted_count == 1
    assert result.decisions[-1].action == "submitted"
    assert result.decisions[-1].live_trading_enabled is False
    order = store.list_orders()[0]
    assert order.shield_decision == PAPER_APPROVED
    assert order.simulated is True


def test_filters_kill_switch_pause_and_exposure_cap_reject_entries() -> None:
    low = MemoryTradingStore()
    scored = run_once(**_kwargs(low, (_candidate(score=Decimal(40)),), _quotes()))
    assert scored.submitted_count == 0
    assert scored.decisions[-1].reason == "below_score"
    assert low.list_orders() == ()

    unknown = MemoryTradingStore()
    blocked_security = run_once(
        **_kwargs(
            unknown,
            (_candidate(security="UNKNOWN", lifecycle="watch_suggested"),),
            _quotes(),
        )
    )
    assert blocked_security.decisions[-1].reason == "security_not_clear"
    assert unknown.list_orders() == ()

    stale = MemoryTradingStore()
    old = run_once(**_kwargs(stale, (_candidate(),), _quotes(), quotes_fresh=False))
    assert old.decisions[-1].reason == "stale_cycle"
    assert stale.list_orders() == ()

    paused_store = MemoryTradingStore()
    from dataclasses import replace

    paused_store.shield = replace(paused_store.shield, halt_entries=True)
    paused = run_once(**_kwargs(paused_store, (_candidate(),), _quotes(), halt_entries=True))
    assert paused.status == "paused"
    assert paused.decisions[-1].reason == "shield_paused"
    assert paused_store.list_orders() == ()

    blocked_store = MemoryTradingStore()
    blocked = run_once(
        **_kwargs(
            blocked_store,
            (_candidate(),),
            _quotes(),
            entries_blocked=True,
            kill_switch="engaged",
        )
    )
    assert blocked.status == "blocked"
    assert blocked.decisions[-1].reason == "kill_switch"
    assert blocked_store.list_orders() == ()

    capped = MemoryTradingStore()
    both = (
        _candidate(),
        _candidate(mint=WSOL, symbol="WSOL", score=Decimal(70)),
    )
    quotes = _quotes()
    quotes[WSOL] = _quote(WSOL)
    limited = run_once(
        **_kwargs(
            capped,
            both,
            quotes,
            max_exposure_fraction=Decimal("0.05"),
            max_entries=2,
        )
    )
    buys = [
        order
        for order in capped.list_orders()
        if order.side is OrderSide.BUY and order.shield_decision == PAPER_APPROVED
    ]
    assert len(buys) == 1
    assert limited.decisions[-1].action == "refused"


def test_stop_exit_uses_a_fresh_pool_and_read_only_stores_nothing() -> None:
    store = MemoryTradingStore()
    opened = run_once(**_kwargs(store, (_candidate(),), _quotes()))
    assert opened.submitted_count == 1
    later = NOW + timedelta(minutes=3)
    crashed = _quotes(later)
    crashed[USDC] = _quote(USDC, base=Decimal(1_000_000), quote=Decimal(400), observed=later)
    closed = run_once(**_kwargs(store, (), crashed, now=later))
    assert any(item.reason == "exit_through_shield" for item in closed.decisions)
    sells = [order for order in store.list_orders() if order.side is OrderSide.SELL]
    assert len(sells) == 1
    assert sells[0].shield_decision == PAPER_APPROVED
    assert sells[0].simulated is True

    idle = MemoryTradingStore()
    skipped = run_once(**_kwargs(idle, (_candidate(),), _quotes(), mode=ExecutionMode.READ_ONLY))
    assert skipped.status == "skipped"
    assert idle.list_orders() == ()
    assert idle.get_strategy("radar-paper") is None


def test_supervisor_flag_is_opt_in_and_read_only_does_not_configure(tmp_path: Path) -> None:
    paper = Settings(
        _env_file=None,
        log_dir=tmp_path,
        execution_mode=ExecutionMode.PAPER,
        database_url=None,
    )
    idle = [item.kind for item in default_workers(paper, allow_radar_network=False)]
    assert idle[-1] == "paper_strategy"
    assert "paper_trader" not in idle
    enabled = default_workers(paper, allow_radar_network=False, allow_paper_trader=True)
    assert enabled[-1].kind == "paper_trader"
    waiting = enabled[-1].tick(NOW)
    assert waiting.status == "not_configured"
    assert "No order was submitted" in waiting.detail
    read_only = Settings(
        _env_file=None,
        log_dir=tmp_path,
        execution_mode=ExecutionMode.READ_ONLY,
        database_url=None,
    )
    skipped = run_stored(read_only, NOW)
    assert skipped.status == "skipped"
    assert skipped.decisions == ()


def test_candidate_reserves_and_stale_view_stay_explicit() -> None:
    parsed = candidate_from_analysis(
        USDC,
        "USDC",
        Decimal(80),
        "watch_suggested",
        "fresh",
        "APPROVED_FOR_FURTHER_ANALYSIS",
        {"price": "0.001", "base_reserve": "1000000", "quote_reserve": "1000"},
    )
    assert parsed.base_reserve == Decimal(1000000)
    assert parsed.quote_reserve == Decimal(1000)
    missing = candidate_from_analysis(USDC, None, None, "ranked", "stale", "UNKNOWN", {})
    assert missing.base_reserve is None
    assert missing.symbol == "TOKEN"
    view = build_paper_trader_view(
        StoredTraderCycle(
            "running",
            "released",
            False,
            False,
            "Orders go through Shield. Live trading stays locked.",
            NOW - timedelta(hours=2),
        ),
        (StoredTraderDecision("USDC", "refused", "below_score", "40.00", NOW),),
        (Decimal(10), None, Decimal("10.1")),
        now=NOW,
        stale_after_seconds=360,
        bankroll=Decimal(10),
    )
    assert view.status == "stale"
    assert view.live_trading_enabled is False
    assert view.equity_points == (Decimal(10), Decimal("10.1"))
    assert view.decisions == ("USDC refused below_score (score 40.00)",)
    assert view.kill_switch == "released"


def test_paper_trade_fraction_cannot_exceed_the_exposure_cap(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            log_dir=tmp_path,
            paper_per_trade_fraction=Decimal("0.50"),
            paper_max_exposure_fraction=Decimal("0.10"),
        )


def test_dashboard_shows_the_trader_log(qtbot) -> None:  # type: ignore[no-untyped-def]
    page = DashboardPage()
    qtbot.addWidget(page)
    view = build_paper_trader_view(
        StoredTraderCycle(
            "running",
            "released",
            False,
            False,
            "Orders go through Shield. Live trading stays locked.",
            NOW,
        ),
        (StoredTraderDecision("USDC", "submitted", "shield_path", "80.00", NOW),),
        (Decimal(10), Decimal("10.2")),
        now=NOW,
        stale_after_seconds=360,
        bankroll=Decimal(10),
    )
    page.show_trader(view, (), ())
    assert page.trader_card.state_label.text() == "running"
    assert page.kill_card.state_label.text() == "released"
    assert len(page.equity._points) == 2
    assert "shield_path" in page.trader_decisions.text()
    labels = [item.text() for item in page.findChildren(QLabel)]
    assert "Paper trader" in labels


def _kwargs(
    store: MemoryTradingStore,
    candidates: tuple[RadarCandidate, ...],
    quotes: dict[str, PoolQuote],
    *,
    now: datetime = NOW,
    mode: ExecutionMode = ExecutionMode.PAPER,
    quotes_fresh: bool = True,
    entries_blocked: bool = False,
    halt_entries: bool = False,
    kill_switch: str = "released",
    max_exposure_fraction: Decimal = Decimal("0.40"),
    max_entries: int = 1,
    unpriced_writeoff_seconds: int = 1800,
    last_priced_at: dict[str, datetime] | None = None,
    require_price_feed: bool = False,
    feed_marks: dict[str, PoolQuote] | None = None,
    max_mark_age_seconds: int | None = None,
) -> dict[str, object]:
    return {
        "mode": mode,
        "store": store,
        "candidates": candidates,
        "quotes": quotes,
        "cycle_id": 7,
        "quotes_fresh": quotes_fresh,
        "bankroll": Decimal(10),
        "per_trade_fraction": Decimal("0.10"),
        "max_exposure_fraction": max_exposure_fraction,
        "min_score": Decimal(65),
        "stop_fraction": Decimal("0.10"),
        "max_entries": max_entries,
        "max_quote_age_seconds": 120,
        "now": now,
        "entries_blocked": entries_blocked,
        "halt_entries": halt_entries,
        "kill_switch": kill_switch,
        "unpriced_writeoff_seconds": unpriced_writeoff_seconds,
        "last_priced_at": last_priced_at,
        "require_price_feed": require_price_feed,
        "feed_marks": feed_marks,
        "max_mark_age_seconds": max_mark_age_seconds,
    }


def _candidate(
    *,
    mint: str = USDC,
    symbol: str = "USDC",
    score: Decimal = Decimal(80),
    lifecycle: str = "watch_suggested",
    security: str = "APPROVED_FOR_FURTHER_ANALYSIS",
) -> RadarCandidate:
    return RadarCandidate(
        mint=mint,
        symbol=symbol,
        score=score,
        lifecycle=lifecycle,
        freshness="fresh",
        security_category=security,
        price=Decimal("0.001"),
        base_reserve=Decimal(1_000_000),
        quote_reserve=Decimal(1000),
        creation_timestamp=None,
    )


def _quotes(observed: datetime = NOW) -> dict[str, PoolQuote]:
    return {USDC: _quote(USDC, observed=observed)}


def _quote(
    mint: str,
    *,
    base: Decimal = Decimal(1_000_000),
    quote: Decimal = Decimal(1000),
    observed: datetime = NOW,
) -> PoolQuote:
    return PoolQuote(mint, quote / base, base, quote, observed)


@pytest.fixture(autouse=True)
def _risky_security_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the strict security filter regardless of the local .env."""

    from trading.paper_trader import loop

    monkeypatch.setattr(loop, "_allow_risky", lambda: False)


def test_risky_security_flag_allows_caution_but_never_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from trading.paper_trader import loop

    monkeypatch.setattr(loop, "_allow_risky", lambda: True)
    assert loop._security_ok("CAUTION")
    assert loop._security_ok("HIGH_RISK")
    assert loop._security_ok("UNKNOWN")
    assert not loop._security_ok("REJECTED")


def test_unpriced_position_is_written_off_after_the_grace_period() -> None:
    store = MemoryTradingStore()
    opened = run_once(**_kwargs(store, (_candidate(),), _quotes()))
    assert opened.submitted_count == 1
    position = next(item for item in store.list_positions() if item.quantity > 0)
    remaining = position.quantity
    average = position.average_price
    assert average is not None
    later = NOW + timedelta(seconds=1800)
    closed = run_once(**_kwargs(store, (), {}, now=later))
    assert any(
        item.action == "exited" and item.reason == "unpriced_writeoff" for item in closed.decisions
    )
    sells = [order for order in store.list_orders() if order.side is OrderSide.SELL]
    assert len(sells) == 1
    assert sells[0].simulated is True
    assert sells[0].state is OrderState.CONFIRMED
    assert sells[0].fill_price == Decimal(0)
    assert sells[0].shield_decision == PAPER_APPROVED
    assert all(item.quantity == 0 for item in store.list_positions())
    assert closed.open_positions == 0
    assert closed.equity_quote is not None
    flat = store.list_positions()[0]
    assert flat.realized_pnl_quote == (Decimal(0) - average) * remaining
    assert closed.equity_quote == Decimal(10) + flat.realized_pnl_quote
    assert closed.realized_quote == flat.realized_pnl_quote


def test_unpriced_position_is_held_before_the_writeoff_grace() -> None:
    store = MemoryTradingStore()
    run_once(**_kwargs(store, (_candidate(),), _quotes()))
    later = NOW + timedelta(seconds=1799)
    held = run_once(**_kwargs(store, (), {}, now=later))
    assert any(item.reason == "mark_missing" and item.action == "held" for item in held.decisions)
    assert not any(item.reason == "unpriced_writeoff" for item in held.decisions)
    assert all(order.side is OrderSide.BUY for order in store.list_orders())
    assert held.equity_quote is None
    assert any(item.quantity > 0 for item in store.list_positions())


def test_writeoff_does_not_run_in_read_only_mode() -> None:
    store = MemoryTradingStore()
    run_once(**_kwargs(store, (_candidate(),), _quotes()))
    later = NOW + timedelta(hours=1)
    skipped = run_once(**_kwargs(store, (), {}, now=later, mode=ExecutionMode.READ_ONLY))
    assert skipped.status == "skipped"
    assert skipped.decisions == ()
    assert all(order.side is OrderSide.BUY for order in store.list_orders())
    assert any(item.quantity > 0 for item in store.list_positions())


def test_priced_position_is_not_written_off() -> None:
    store = MemoryTradingStore()
    run_once(**_kwargs(store, (_candidate(),), _quotes()))
    later = NOW + timedelta(seconds=1800)
    result = run_once(**_kwargs(store, (), _quotes(later), now=later))
    assert not any(item.reason == "unpriced_writeoff" for item in result.decisions)
    assert any(item.quantity > 0 for item in store.list_positions())
    assert result.equity_quote is not None


def test_writeoff_uses_last_priced_history_not_only_the_last_fill() -> None:
    store = MemoryTradingStore()
    run_once(**_kwargs(store, (_candidate(),), _quotes()))
    later = NOW + timedelta(seconds=1800)
    result = run_once(
        **_kwargs(
            store,
            (),
            {},
            now=later,
            last_priced_at={USDC: later - timedelta(seconds=100)},
        )
    )
    assert any(item.reason == "mark_missing" for item in result.decisions)
    assert not any(item.reason == "unpriced_writeoff" for item in result.decisions)
    assert any(item.quantity > 0 for item in store.list_positions())


def test_writeoff_clears_exposure_so_a_new_entry_can_be_sized() -> None:
    store = MemoryTradingStore()
    run_once(**_kwargs(store, (_candidate(),), _quotes()))
    later = NOW + timedelta(seconds=1800)
    quotes = {WSOL: _quote(WSOL, observed=later)}
    result = run_once(
        **_kwargs(store, (_candidate(mint=WSOL, symbol="WSOL"),), quotes, now=later)
    )
    assert any(item.reason == "unpriced_writeoff" for item in result.decisions)
    assert not any(item.reason == "exposure_unpriced" for item in result.decisions)
    assert result.equity_quote is not None
    buys = [order for order in store.list_orders() if order.side is OrderSide.BUY]
    assert len(buys) == 2


def test_paper_unpriced_writeoff_seconds_default(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, log_dir=tmp_path)
    assert settings.paper_unpriced_writeoff_seconds == 1800
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_dir=tmp_path, paper_unpriced_writeoff_seconds=59)


def test_collect_marks_falls_back_to_stored_radar_when_live_refresh_fails() -> None:
    later = NOW + timedelta(seconds=200)
    seed = {USDC: _quote(USDC, observed=NOW)}
    stored = {USDC: _quote(USDC, observed=NOW)}
    marks = collect_marks(
        (USDC,),
        now=later,
        max_age_seconds=120,
        seeded=seed,
        refreshed={},
        stored=stored,
        stored_max_age_seconds=600,
    )
    assert USDC in marks
    assert marks[USDC] is stored[USDC]
    live = {USDC: _quote(USDC, base=Decimal(2_000_000), quote=Decimal(1000), observed=later)}
    preferred = collect_marks(
        (USDC,),
        now=later,
        max_age_seconds=120,
        seeded=seed,
        refreshed=live,
        stored=stored,
        stored_max_age_seconds=600,
    )
    assert preferred[USDC] is live[USDC]
    expired = collect_marks(
        (USDC,),
        now=NOW + timedelta(seconds=700),
        max_age_seconds=120,
        seeded=seed,
        refreshed={},
        stored=stored,
        stored_max_age_seconds=600,
    )
    assert expired == {}
    assert stored_mark_max_age_seconds(120, 1800) == 900


def test_stored_radar_fallback_can_mark_an_open_position() -> None:
    store = MemoryTradingStore()
    opened = run_once(**_kwargs(store, (_candidate(),), _quotes()))
    assert opened.submitted_count == 1
    later = NOW + timedelta(seconds=200)
    stale = {USDC: _quote(USDC, observed=NOW)}
    held = run_once(
        **_kwargs(
            store,
            (),
            stale,
            now=later,
            max_mark_age_seconds=600,
        )
    )
    assert any(item.reason == "within_plan" for item in held.decisions)
    assert held.equity_quote is not None
    assert not any(item.reason == "mark_missing" for item in held.decisions)


def test_price_feed_gate_refuses_when_the_mark_is_missing_or_diverges() -> None:
    missing = MemoryTradingStore()
    refused = run_once(
        **_kwargs(missing, (_candidate(),), _quotes(), require_price_feed=True, feed_marks={})
    )
    assert refused.submitted_count == 0
    assert refused.decisions[-1].reason == "no_price_feed"
    assert missing.list_orders() == ()

    skewed = MemoryTradingStore()
    far = {USDC: _quote(USDC, base=Decimal(1_000_000), quote=Decimal(200))}
    refused_far = run_once(
        **_kwargs(
            skewed,
            (_candidate(),),
            _quotes(),
            require_price_feed=True,
            feed_marks=far,
        )
    )
    assert refused_far.decisions[-1].reason == "no_price_feed"
    assert skewed.list_orders() == ()


def test_price_feed_gate_allows_a_confirming_mark() -> None:
    store = MemoryTradingStore()
    close = {USDC: _quote(USDC, base=Decimal(1_000_000), quote=Decimal(1100))}
    result = run_once(
        **_kwargs(
            store,
            (_candidate(),),
            _quotes(),
            require_price_feed=True,
            feed_marks=close,
        )
    )
    assert result.submitted_count == 1
    assert result.decisions[-1].action == "submitted"
    assert store.list_orders()[0].simulated is True


def test_price_feed_gate_can_be_disabled() -> None:
    store = MemoryTradingStore()
    result = run_once(
        **_kwargs(store, (_candidate(),), _quotes(), require_price_feed=False, feed_marks={})
    )
    assert result.submitted_count == 1


def test_paper_require_price_feed_defaults_on(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, log_dir=tmp_path)
    assert settings.paper_require_price_feed is True

