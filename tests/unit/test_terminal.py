"""Phase 7 terminal read model. These tests cannot enable live trading."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from config.settings import Settings
from domain.exceptions import TradingValidationError
from domain.shield import (
    PAPER_APPROVED,
    CampaignRecord,
    DailyBaseline,
    EmergencyFlag,
    ShieldDecisionRecord,
    ShieldSnapshot,
)
from domain.status import ComponentStatus, StatusSnapshot
from domain.terminal import NotificationCategory, NotificationRecord
from domain.trading import (
    OrderRecord,
    OrderSide,
    OrderState,
    PositionRecord,
    SimulationOutcome,
    StrategyRecord,
    StrategyState,
    TradingSnapshot,
)
from intelligence.store import AnalysisDetail, CycleSnapshot, DiscoveryRow, RankRow
from shield.engine import initial_snapshot, pause_entries, resume_entries
from terminal.analytics import build_analytics
from terminal.assemble import assemble
from terminal.marks import Mark, marks_for
from terminal.notifications import build_notifications, in_quiet, unseen
from terminal.portfolio import build_portfolio
from terminal.present import snapshot_payload
from terminal.profiles import (
    default_preferences,
    default_profile,
    normalize_preferences,
    normalize_profile,
)

MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
NOW = datetime(2026, 11, 11, 12, tzinfo=UTC)


def test_missing_mark_is_not_stored_as_zero_pnl() -> None:
    view = build_portfolio(_book(), initial_snapshot(), {}, now=NOW)
    assert view.positions[0].current_price is None
    assert view.positions[0].unrealized_pnl is None
    assert view.unrealized is None
    assert view.sol_balance_detail.startswith("No wallet")
    assert view.usd_detail.startswith("No USD")
    assert view.verified_equity is None


def test_verified_equity_and_mark_stay_distinct() -> None:
    view = build_portfolio(_book(), _shield(Decimal("10")), _marks(Decimal("3")), now=NOW)
    assert view.verified_equity == Decimal("10")
    assert view.positions[0].position_value == Decimal("6")
    assert view.positions[0].unrealized_pnl == Decimal("4")
    assert view.available == Decimal("4")
    assert view.realized == Decimal("1")
    assert view.win_rate == Decimal("1")
    assert view.active_strategies == 1
    assert "not a wallet" in view.verified_equity_detail


def test_candle_close_mark_is_labeled_and_not_a_fill() -> None:
    found = marks_for(_cycle())
    assert "candle close" in found[MINT].source
    assert "not a fill" in found[MINT].source


def test_pause_does_not_change_limits_or_submit_an_order() -> None:
    original = initial_snapshot()
    paused, notices = pause_entries(original, NOW)
    assert paused.halt_entries is True
    assert paused.limits == original.limits
    assert notices[0].kind == "operator_pause"
    again, empty = pause_entries(paused, NOW)
    assert again is paused
    assert empty == ()
    breached = _copy_shield(
        original,
        breach_latched=True,
        breach_reasons=("daily_loss",),
        halt_entries=True,
    )
    with pytest.raises(TradingValidationError, match="breach"):
        resume_entries(breached, NOW)
    halted = _copy_shield(
        original,
        halt_entries=True,
        emergencies=(EmergencyFlag(MINT, ("trading_restriction",), NOW, True),),
    )
    with pytest.raises(TradingValidationError, match="emergency halt"):
        resume_entries(halted, NOW)


def test_profile_and_preferences_cannot_enable_live_or_telegram() -> None:
    with pytest.raises(TradingValidationError, match="live"):
        normalize_profile("paper-one", "Paper one", (), active=True, live_trading_enabled=True)
    with pytest.raises(TradingValidationError, match="secret"):
        normalize_profile("paper-one", "seed phrase", (), active=False)
    profile = normalize_profile("paper-one", "Paper one", ("core-slot",), active=False)
    assert profile.live_trading_enabled is False
    assert "Shield" in profile.authority_note
    with pytest.raises(TradingValidationError, match="Telegram"):
        normalize_preferences(
            enabled_categories=("new_token",),
            quiet_start_minute=None,
            quiet_end_minute=None,
            minimum_repeat_seconds=3600,
            telegram_delivery=True,
        )
    prefs = normalize_preferences(
        enabled_categories=("new_token",),
        quiet_start_minute=0,
        quiet_end_minute=60,
        minimum_repeat_seconds=3600,
    )
    assert prefs.telegram_delivery is False
    assert NotificationCategory.EMERGENCY_STOP.value in prefs.enabled_categories


def test_quiet_period_withholds_research_and_keeps_critical_notices() -> None:
    assert in_quiet(NOW, 0, 13 * 60) is True
    assert in_quiet(NOW, 13 * 60, 14 * 60) is False
    prefs = normalize_preferences(
        enabled_categories=("new_token", "high_score", "database_failure"),
        quiet_start_minute=0,
        quiet_end_minute=13 * 60,
        minimum_repeat_seconds=3600,
    )
    drafts = build_notifications(
        trading=TradingSnapshot((), (), ()),
        shield=initial_snapshot(),
        notices=(),
        decisions=(),
        cycle=_cycle(),
        status=_status("unreachable", "running"),
        preferences=prefs,
        now=NOW,
    )
    by_category = {item.category: item for item in drafts}
    assert by_category["new_token"].withheld is True
    assert by_category["database_failure"].withheld is False
    assert "not an entry" in by_category["high_score"].detail
    stored = (
        NotificationRecord(
            by_category["new_token"].dedup_key,
            "new_token",
            MINT,
            "stored",
            NOW,
            NOW,
            True,
            False,
        ),
    )
    assert all(item.category != "new_token" for item in unseen(stored, drafts))


def test_analytics_does_not_invent_sharpe_or_deploy_research() -> None:
    short = tuple(_baseline(index) for index in range(10))
    view = build_analytics((), (), short, (_report(True), _report(False)))
    assert view.sharpe is None
    assert view.sharpe_reason in {"no_equity_curve", "not_statistically_meaningful"}
    assert len(view.research) == 1
    assert view.research[0].parameters_deployed is False
    measured = build_analytics((), (), tuple(_baseline(index) for index in range(32)), ())
    assert measured.sharpe is not None
    assert len(measured.daily) == 31


def test_analyst_cannot_authorize_and_does_not_call_a_model() -> None:
    snapshot = _assembled()
    assert snapshot.analyst.external_model_called is False
    assert snapshot.analyst.provider == "stored-evidence"
    assert snapshot.settings.live_control_present is False
    assert snapshot.settings.live_trading_enabled is False
    assert all(item.authorizes_order is False for item in snapshot.analyst.findings)
    payload = snapshot_payload(snapshot)
    assert payload["live_trading_enabled"] is False
    assert payload["telegram_delivery"] is False
    assert "database_url" not in payload
    assert "api_key" not in str(payload)


def test_take_profit_decision_is_a_notice_not_a_fill() -> None:
    decision = ShieldDecisionRecord(
        "paper-1",
        MINT,
        "SELL",
        PAPER_APPROVED,
        None,
        Decimal("1"),
        Decimal("1"),
        "take_profit",
        False,
        "paper",
        NOW,
    )
    drafts = build_notifications(
        trading=TradingSnapshot((), (), ()),
        shield=initial_snapshot(),
        notices=(),
        decisions=(decision,),
        cycle=None,
        status=None,
        preferences=default_preferences(),
        now=NOW,
    )
    assert [item.category for item in drafts] == ["take_profit"]
    assert "simulated" in drafts[0].detail


def test_terminal_routes_reject_live_and_telegram(tmp_path) -> None:  # type: ignore[no-untyped-def]
    secret = "local-test-token"
    settings = Settings(_env_file=None, log_dir=tmp_path, api_token=secret)
    app = create_app(settings)
    app.state.terminal_repository = _FakeTerminal(_assembled())
    app.state.terminal_clock = lambda: NOW
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {secret}"}
    assert client.get("/terminal/snapshot").status_code == 401
    body = client.get("/terminal/snapshot", headers=headers)
    assert body.status_code == 200
    assert body.json()["live_trading_enabled"] is False
    assert body.json()["authorizes_order"] is False
    refused = client.put(
        "/terminal/profiles",
        headers=headers,
        json={"profile_id": "paper-one", "name": "Paper one", "live_trading_enabled": True},
    )
    assert refused.status_code == 422
    telegram = client.put(
        "/terminal/notifications/preferences",
        headers=headers,
        json={
            "enabled_categories": ["new_token"],
            "minimum_repeat_seconds": 3600,
            "telegram_delivery": True,
        },
    )
    assert telegram.status_code == 422
    paused = client.post("/terminal/controls/pause", headers=headers)
    assert paused.status_code == 200
    assert paused.json() == {
        "halt_entries": True,
        "live_trading_enabled": False,
        "order_submitted": False,
    }


class _FakeTerminal:
    def __init__(self, snapshot: object) -> None:
        self.snapshot = snapshot

    def load(self, status: object, now: datetime) -> object:
        del status, now
        return self.snapshot

    def save_profile(
        self,
        profile_id: str,
        name: str,
        strategy_ids: tuple[str, ...],
        *,
        active: bool,
        signal_threshold: str | None,
        now: datetime,
    ) -> object:
        del now
        return normalize_profile(
            profile_id,
            name,
            strategy_ids,
            active=active,
            signal_threshold=signal_threshold,
            live_trading_enabled=False,
        )

    def activate_profile(self, profile_id: str, now: datetime) -> None:
        del profile_id, now

    def save_preferences(self, preferences: object, now: datetime) -> None:
        del preferences, now

    def pause_entries(self, now: datetime) -> None:
        del now

    def resume_entries(self, now: datetime) -> None:
        del now


def _assembled() -> object:
    return assemble(
        trading=TradingSnapshot((), (), ()),
        shield=initial_snapshot(),
        notices=(),
        decisions=(),
        cycle=None,
        simulation_reports=(),
        profiles=(default_profile(),),
        preferences=default_preferences(),
        existing_notifications=(),
        execution_mode="READ_ONLY",
        database_configured=False,
        gmgn_configured=False,
        api_host="127.0.0.1",
        api_port=8787,
        status=None,
        now=NOW,
    )


def _book() -> TradingSnapshot:
    order = OrderRecord(
        "paper-1",
        "paper-1",
        "core-slot",
        MINT,
        "USDC",
        OrderSide.BUY,
        OrderState.CONFIRMED,
        Decimal("2"),
        Decimal("2"),
        Decimal("1"),
        Decimal("1"),
        Decimal("0"),
        Decimal("0"),
        "SOL",
        6,
        6,
        9,
        SimulationOutcome.FILL,
        PAPER_APPROVED,
        True,
        None,
        NOW,
        NOW,
    )
    position = PositionRecord(
        MINT, Decimal("2"), Decimal("1"), Decimal("2"), Decimal("1"), "SOL", NOW
    )
    strategy = StrategyRecord("core-slot", "Core", StrategyState.RUNNING, (), NOW, NOW)
    return TradingSnapshot((order,), (position,), (strategy,))


def _shield(equity: Decimal) -> ShieldSnapshot:
    base = initial_snapshot()
    closed = CampaignRecord(
        "camp-1",
        MINT,
        "core-slot",
        NOW - timedelta(hours=2),
        NOW,
        Decimal("2"),
        Decimal("2"),
        Decimal("1"),
        "paper-1",
        None,
        None,
        None,
        None,
        None,
        "clear",
    )
    return _copy_shield(
        base,
        high_water_equity=equity,
        daily=(DailyBaseline(date(2026, 11, 11), equity, equity, False, NOW),),
        campaigns=(closed,),
    )


def _copy_shield(base: ShieldSnapshot, **changes: object) -> ShieldSnapshot:
    values = {
        "limits": base.limits,
        "high_water_equity": base.high_water_equity,
        "consecutive_losses": base.consecutive_losses,
        "breach_latched": base.breach_latched,
        "breach_reasons": base.breach_reasons,
        "halt_entries": base.halt_entries,
        "daily": base.daily,
        "campaigns": base.campaigns,
        "stops": base.stops,
        "emergencies": base.emergencies,
    }
    values.update(changes)
    return ShieldSnapshot(**values)  # type: ignore[arg-type]


def _marks(price: Decimal) -> dict[str, Mark]:
    return {MINT: Mark(price, "radar cycle 1 ranking", NOW.isoformat())}


def _baseline(index: int) -> DailyBaseline:
    day = date(2026, 1, 1) + timedelta(days=index)
    equity = Decimal(100 + index)
    return DailyBaseline(day, equity, equity, False, NOW)


def _report(deployed: bool) -> dict[str, object]:
    return {
        "run_id": "run-1",
        "kind": "compare",
        "strategy_id": "momentum",
        "parameters_deployed": deployed,
        "performance": {"net_profit": "1.5", "trade_count": 2, "max_drawdown": "0.1"},
    }


def _cycle() -> CycleSnapshot:
    discovery = DiscoveryRow(
        "new_launch",
        "sol",
        MINT,
        "USDC",
        "USD Coin",
        "1",
        None,
        None,
        None,
        None,
        None,
        "route",
        None,
    )
    rank = RankRow(
        1,
        "sol",
        MINT,
        "USDC",
        "USD Coin",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "missing",
        "missing",
        "clear",
        "70",
        "0.5",
        "research",
        "APPROVED_FOR_FURTHER_ANALYSIS",
        (),
    )
    detail = AnalysisDetail(
        "sol",
        MINT,
        "USDC",
        "USD Coin",
        "Stored explanation.",
        "APPROVED_FOR_FURTHER_ANALYSIS",
        "70",
        "clear",
        "observed",
        "observed",
        "missing",
        None,
        None,
        None,
        None,
        (),
        (),
        (),
        ((None, "1", "2", "1", "4"),),
    )
    return CycleSnapshot(
        7,
        "completed",
        NOW.isoformat(),
        NOW.isoformat(),
        "sol",
        1,
        1,
        0,
        1,
        1,
        None,
        (discovery,),
        (rank,),
        (detail,),
        (),
    )


def _status(database: str, backend: str) -> StatusSnapshot:
    return StatusSnapshot(
        "CYVORA",
        "0.7.0",
        "7",
        "local",
        "READ_ONLY",
        False,
        ComponentStatus("running", "running"),
        ComponentStatus(database, "withheld"),
        ComponentStatus(backend, "withheld"),
        ComponentStatus("not_configured", "not configured"),
    )
