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
from domain.trading import OrderSide, StrategyState
from operations.assembly import default_workers
from terminal.paper_trader import build_paper_trader_view
from trading.memory_store import MemoryTradingStore
from trading.paper_trader.candidates import candidate_from_analysis
from trading.paper_trader.loop import run_once
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
