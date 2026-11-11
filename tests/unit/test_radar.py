"""Radar scoring, a mocked cycle, and the authenticated API."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx2
import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.desktop.windows.main_window import MainWindow
from config.settings import Settings
from integrations.gmgn.client import GMGNClient
from integrations.gmgn.models import TokenInfo, TokenSecurity
from intelligence.cycle import run_radar_cycle
from intelligence.indicators import macd_histogram, price_return, rsi, volume_acceleration
from intelligence.memory_store import MemoryRadarStore
from intelligence.opportunity import ScoreInputs, rank_results, score_token
from intelligence.schedule import RadarScheduler, next_delay_seconds
from intelligence.token_security import assess_security

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
WSOL = "So11111111111111111111111111111111111111112"
BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"


def test_rsi_is_100_for_a_rising_series_and_missing_when_short() -> None:
    rising = tuple(Decimal(index) for index in range(1, 20))
    assert rsi(rising) == Decimal(100)
    falling = tuple(Decimal(30 - index) for index in range(16))
    assert rsi(falling) == Decimal(0)
    assert rsi(tuple(Decimal(1) for _ in range(20))) is None
    assert rsi((Decimal(1), Decimal(2))) is None


def test_macd_and_volume_need_their_windows() -> None:
    closes = tuple(Decimal(index) for index in range(1, 40))
    assert macd_histogram(closes) is not None
    assert macd_histogram(closes[:10]) is None
    volumes = tuple(Decimal(1) for _ in range(5)) + tuple(Decimal(3) for _ in range(5))
    assert volume_acceleration(volumes) == Decimal(3)
    assert volume_acceleration(volumes[:5]) is None
    assert price_return((Decimal(1), Decimal("1.1"))) == Decimal("0.1")


def test_honeypot_is_rejected_and_missing_security_is_unknown() -> None:
    rejected = assess_security(TokenSecurity(is_honeypot=True), None)
    assert rejected.category == "REJECTED"
    assert rejected.score == Decimal("0.00")
    unknown = assess_security(None, None)
    assert unknown.category == "UNKNOWN"
    assert unknown.score is None


def test_clean_security_can_be_approved_for_further_analysis() -> None:
    security = TokenSecurity(
        is_honeypot=False,
        renounced_mint=True,
        renounced_freeze_account=True,
        buy_tax=Decimal(0),
        sell_tax=Decimal(0),
        top_10_holder_rate=Decimal("0.2"),
        creator_balance_rate=Decimal("0.01"),
        is_wash_trading=False,
        rug_ratio=Decimal(0),
        sniper_count=0,
        burn_status="reported",
    )
    result = assess_security(security, TokenInfo())
    assert result.category == "APPROVED_FOR_FURTHER_ANALYSIS"
    assert result.score == Decimal(85)


def test_missing_honeypot_flag_is_not_treated_as_safe() -> None:
    security = TokenSecurity(
        renounced_mint=True,
        renounced_freeze_account=True,
        buy_tax=Decimal(0),
        sell_tax=Decimal(0),
        is_wash_trading=False,
        rug_ratio=Decimal(0),
        sniper_count=0,
        top_10_holder_rate=Decimal("0.2"),
        creator_balance_rate=Decimal(0),
        burn_status="burn",
    )
    result = assess_security(security, None)
    assert result.category == "CAUTION"
    assert any("not evidence" in warning for warning in result.warnings)


def test_score_caps_a_rejected_token_and_never_authorizes_entry() -> None:
    scored = score_token(
        ScoreInputs(
            security=TokenSecurity(is_honeypot=True),
            info=None,
            pool=None,
            candles=(),
            holders=None,
            traders=None,
            rank_changes=(),
            rank_extra=None,
            stale_candles=False,
            discovered_liquidity=Decimal(100000),
            prior_liquidity=None,
            sources=("trending",),
        )
    )
    assert scored.decision == "REJECTED"
    assert scored.entry_consideration == "not_authorized"
    assert scored.total is not None
    assert scored.total <= Decimal(25)


def test_rank_puts_rejected_tokens_last() -> None:
    approved = score_token(
        ScoreInputs(
            security=TokenSecurity(
                is_honeypot=False,
                renounced_mint=True,
                renounced_freeze_account=True,
                buy_tax=Decimal(0),
                sell_tax=Decimal(0),
                top_10_holder_rate=Decimal("0.2"),
                creator_balance_rate=Decimal(0),
                is_wash_trading=False,
                rug_ratio=Decimal(0),
                sniper_count=0,
                burn_status="none",
            ),
            info=TokenInfo(liquidity=Decimal(50000)),
            pool=None,
            candles=(),
            holders=None,
            traders=None,
            rank_changes=(Decimal("0.1"), Decimal("0.2"), Decimal("-0.1")),
            rank_extra=None,
            stale_candles=False,
            discovered_liquidity=Decimal(50000),
            prior_liquidity=None,
            sources=("trending", "new_launch"),
        )
    )
    rejected = score_token(
        ScoreInputs(
            security=TokenSecurity(is_honeypot=True),
            info=None,
            pool=None,
            candles=(),
            holders=None,
            traders=None,
            rank_changes=(),
            rank_extra=None,
            stale_candles=False,
            discovered_liquidity=None,
            prior_liquidity=None,
            sources=("trending",),
        )
    )
    ranked = rank_results([("good", approved, "b"), ("bad", rejected, "a")])
    assert ranked[0][0] == 1
    assert ranked[0][1] == "good"
    assert ranked[-1][1] == "bad"
    assert approved.confirmation_bonus == Decimal(5)


def test_delay_grows_after_a_partial_cycle() -> None:
    from intelligence.cycle import CycleResult

    partial = CycleResult(1, "partial", 10, 4, 3, 1, 1, 1, (), None)
    assert next_delay_seconds(120, partial) == 240
    clean = CycleResult(1, "completed", 10, 4, 3, 1, 1, 0, (), None)
    assert next_delay_seconds(120, clean) == 120


@pytest.mark.asyncio
async def test_scheduler_stops_after_the_requested_cycles() -> None:
    from intelligence.cycle import CycleResult

    calls = {"count": 0}

    async def runner() -> CycleResult:
        calls["count"] += 1
        return CycleResult(calls["count"], "completed", 1, 1, 1, 1, 1, 0, (), None)

    async def sleeper(_seconds: float) -> None:
        return None

    results = await RadarScheduler(runner, interval_seconds=120, sleeper=sleeper).run(max_cycles=2)
    assert len(results) == 2
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_mocked_cycle_discovers_scores_and_stores_without_a_trade() -> None:
    secret = "gmgn-test-key-not-real"
    seen: list[str] = []
    now = [1_700_000_000.0]

    def clock() -> float:
        return now[0]

    async def sleeper(seconds: float) -> None:
        now[0] += seconds

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.path)
        assert secret not in str(request.url)
        if request.url.path == "/v1/market/rank":
            return _ok({"rank": [_rank(USDC, "0.2"), _rank(WSOL, "0.1"), _rank(BONK, "-0.1")]})
        if request.url.path == "/v1/trenches":
            return _ok({"new_creation": []})
        if request.url.path == "/v1/token/info":
            return _ok(
                {
                    "address": USDC,
                    "symbol": "USDC",
                    "name": "USD Coin",
                    "liquidity": "80000",
                    "price": {"price": "1.00"},
                    "wallet_tags_stat": {"smart_wallets": 2, "whale_wallets": 1},
                    "stat": {"top_10_holder_rate": "0.2", "creator_hold_rate": "0"},
                }
            )
        if request.url.path == "/v1/token/security":
            return _ok(
                {
                    "is_honeypot": False,
                    "renounced_mint": True,
                    "renounced_freeze_account": True,
                    "buy_tax": "0",
                    "sell_tax": "0",
                    "top_10_holder_rate": "0.2",
                    "creator_balance_rate": "0",
                    "is_wash_trading": False,
                    "rug_ratio": "0",
                    "sniper_count": 0,
                    "burn_status": "none",
                }
            )
        if request.url.path == "/v1/token/pool_info":
            return _ok({"address": "pool", "liquidity": "80000"})
        if request.url.path == "/v1/market/token_kline":
            stamp = 1_700_000_000
            return _ok(
                {
                    "list": [
                        _candle(stamp - 60, "1.0", "1.1"),
                        _candle(stamp, "1.1", "1.2"),
                    ]
                }
            )
        raise AssertionError(request.url.path)

    client = GMGNClient(
        secret,
        transport=httpx2.MockTransport(handler),
        clock=clock,
        sleeper=sleeper,
        client_id_factory=lambda: "client-id-test",
    )
    settings = Settings(
        _env_file=None,
        gmgn_api_key=secret,
        radar_trending_limit=3,
        radar_launch_limit=1,
        radar_analyse_limit=1,
        radar_budget_weight=10,
        radar_kline_lookback_seconds=3600,
    )
    store = MemoryRadarStore()
    result = await run_radar_cycle(
        settings,
        store,
        client=client,
        now=datetime.fromtimestamp(1_700_000_000, UTC),
    )
    assert result.cycle_id == 1
    assert result.analysed_count == 1
    assert result.status == "completed"
    assert result.lines
    assert "entry=not_authorized" in result.lines[0]
    assert secret not in result.public_report()
    assert all(not path.startswith("/v1/trade/") for path in seen)
    snapshot = store.latest_snapshot()
    assert snapshot is not None
    assert snapshot.rankings[0].symbol == "USDC"
    assert snapshot.rankings[0].entry_consideration == "not_authorized"
    assert snapshot.discoveries


@pytest.mark.asyncio
async def test_cycle_stops_sending_after_a_rate_limit() -> None:
    seen: list[str] = []
    now = [1_700_000_000.0]

    def clock() -> float:
        return now[0]

    async def sleeper(seconds: float) -> None:
        now[0] += seconds

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.path)
        if request.url.path == "/v1/market/rank":
            return _ok({"rank": [_rank(USDC, "0.2")]})
        if request.url.path == "/v1/trenches":
            return _ok({"new_creation": []})
        if request.url.path == "/v1/token/info":
            return _ok({"address": USDC, "symbol": "USDC", "liquidity": "80000"})
        if request.url.path == "/v1/token/security":
            return httpx2.Response(
                429,
                json={
                    "code": 429,
                    "error": "RATE_LIMIT_BANNED",
                    "reset_at": 1_900_000_000,
                },
            )
        raise AssertionError(request.url.path)

    client = GMGNClient(
        "gmgn-test-key-not-real",
        transport=httpx2.MockTransport(handler),
        clock=clock,
        sleeper=sleeper,
        client_id_factory=lambda: "client-id-test",
    )
    settings = Settings(
        _env_file=None,
        gmgn_api_key="gmgn-test-key-not-real",
        radar_trending_limit=1,
        radar_launch_limit=1,
        radar_analyse_limit=1,
        radar_budget_weight=10,
    )
    result = await run_radar_cycle(
        settings,
        MemoryRadarStore(),
        client=client,
        now=datetime.fromtimestamp(1_700_000_000, UTC),
    )
    assert result.rate_limit_hits == 1
    assert result.status == "partial"
    assert "/v1/token/pool_info" not in seen
    assert "/v1/market/token_kline" not in seen


def test_radar_routes_require_a_token_and_do_not_trade(tmp_path) -> None:  # type: ignore[no-untyped-def]
    secret = "local-test-token"
    settings = Settings(
        _env_file=None, log_dir=tmp_path, api_token=secret, gmgn_api_key="gmgn-test-key-not-real"
    )
    app = create_app(settings)
    store = MemoryRadarStore()
    app.state.radar_store = store

    async def runner(active: Settings, radar_store: MemoryRadarStore) -> object:
        del active, radar_store
        from intelligence.cycle import CycleResult

        return CycleResult(
            1, "completed", 10, 4, 3, 0, 1, 0, ("rank=1 entry=not_authorized",), None
        )

    app.state.radar_runner = runner
    client = TestClient(app)
    assert client.get("/radar/latest").status_code == 401
    denied = client.get("/radar/latest", headers={"Authorization": "Bearer wrong"})
    assert denied.status_code == 401
    assert secret not in denied.text
    ok = client.get("/radar/latest", headers={"Authorization": f"Bearer {secret}"})
    assert ok.status_code == 200
    assert ok.json()["cycle"] is None
    started = client.post("/radar/cycles", headers={"Authorization": f"Bearer {secret}"})
    assert started.status_code == 200
    assert started.json()["entry_consideration"] == "not_authorized"
    added = client.post(
        "/radar/watchlist",
        headers={"Authorization": f"Bearer {secret}"},
        json={"chain": "sol", "address": USDC, "note": "research"},
    )
    assert added.status_code == 200
    assert store.list_watches()[0].active is True
    removed = client.delete(
        f"/radar/watchlist/sol/{USDC}",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert removed.json()["removed"] is True


def test_scanner_page_does_not_invent_tokens(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = MainWindow(Settings(_env_file=None, database_url=None), start_probe=False)
    qtbot.addWidget(window)
    window.show()
    assert "Live Scanner" not in window.navigation.names()
    window.show_page("Live Scanner")
    assert window.stack.currentWidget() is window.scanner
    assert window.page_title.text() == "Live Scanner"
    assert "not configured" in window.scanner.summary.text()
    assert window.scanner.table.rowCount() == 0
    assert window.scanner.run_button.text().startswith("Run one read-only")


def test_intelligence_source_has_no_trade_or_signing_path() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "intelligence"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "/v1/trade/" not in text
    assert "GMGN_PRIVATE_KEY" not in text
    assert "nautilus" not in text.lower()
    assert "def swap" not in text


def _ok(data: dict[str, object]) -> httpx2.Response:
    return httpx2.Response(200, json={"code": 0, "data": data})


def _rank(address: str, change: str) -> dict[str, str]:
    return {
        "address": address,
        "symbol": "USDC" if address == USDC else "OTHER",
        "name": "Example",
        "price": "1",
        "liquidity": "80000",
        "volume": "10",
        "price_change_percent": change,
    }


def _candle(stamp: int, open_: str, close: str) -> dict[str, object]:
    return {
        "time": stamp,
        "open": open_,
        "high": close,
        "low": open_,
        "close": close,
        "volume": "5",
        "amount": "6",
    }
