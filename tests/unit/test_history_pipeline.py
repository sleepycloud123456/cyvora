"""Historical import, quality, and the simulation routes that store them."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.desktop.services.loopback_api import request_json
from backtesting.history import OPERATIONAL_BAR_LIMIT, require_dataset
from backtesting.memory_store import MemorySimulationStore
from backtesting.pipeline import dataset_from_csv, dataset_from_gmgn_candles, dataset_from_parquet
from backtesting.quality import validate_quality
from config.settings import Settings
from domain.enums import ExecutionMode
from domain.exceptions import TradingValidationError
from domain.simulation import HistoricalBar, HistoricalDataset
from integrations.gmgn.models import Candle
from integrations.solana.adapter import adapt_observation
from trading.memory_store import MemoryTradingStore

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
NOTE = "Tokens supplied for this research import, with volume kept as volume."
START = datetime(2026, 11, 11, tzinfo=UTC)


def test_operational_limit_replaces_the_400_bar_and_4_mint_caps() -> None:
    bars = tuple(_bar(index, _mint(index % 5)) for index in range(401))
    checked = require_dataset(_dataset(bars))
    assert len(checked.bars) == 401
    assert len({bar.mint for bar in checked.bars}) == 5
    assert OPERATIONAL_BAR_LIMIT > 400
    with pytest.raises(TradingValidationError, match="Split the series"):
        require_dataset(_dataset(bars[:3]), max_bars=2)
    source = (
        Path(__file__).resolve().parents[2] / "database" / "repositories" / "simulation.py"
    ).read_text(encoding="utf-8")
    assert "candles[:400]" not in source
    assert "radar_import_kept_the_oldest_400_candles" not in source
    assert "OPERATIONAL_BAR_LIMIT" in source


def test_csv_and_parquet_keep_volume_out_of_depth() -> None:
    csv_text = (
        "mint,symbol,observed_at,close,volume,bid,ask\n"
        f"{USDC},USDC,2026-11-11T00:00:00+00:00,0.10,25,0.09,0.11\n"
    )
    csv_dataset = dataset_from_csv(
        csv_text, dataset_id="csv-sample", name="CSV sample", selection_note=NOTE
    )
    bar = csv_dataset.bars[0]
    assert bar.volume_quote == Decimal(25)
    assert bar.base_reserve is None
    assert bar.quote_reserve is None
    assert bar.bid_size is None
    assert bar.ask_size is None
    assert "candle_volume_is_not_executable_depth" in csv_dataset.limitations
    table = pa.table(
        {
            "mint": [USDC],
            "symbol": ["USDC"],
            "observed_at": ["2026-11-11T00:01:00+00:00"],
            "close": ["0.20"],
            "volume": ["7"],
            "bid_size": ["3"],
            "ask_size": ["4"],
            "bid": ["0.19"],
            "ask": ["0.21"],
        }
    )
    payload = io.BytesIO()
    pq.write_table(table, payload)
    parsed = dataset_from_parquet(
        payload.getvalue(),
        dataset_id="parquet-sample",
        name="Parquet sample",
        selection_note=NOTE,
    )
    stored = parsed.bars[0]
    assert stored.volume_quote == Decimal(7)
    assert stored.bid_size == Decimal(3)
    assert stored.base_reserve is None
    floats = pa.table(
        {
            "mint": [USDC],
            "observed_at": ["2026-11-11T00:01:00+00:00"],
            "close": pa.array([0.2], type=pa.float64()),
        }
    )
    raw = io.BytesIO()
    pq.write_table(floats, raw)
    with pytest.raises(TradingValidationError, match="binary float"):
        dataset_from_parquet(
            raw.getvalue(),
            dataset_id="parquet-float",
            name="Parquet float",
            selection_note=NOTE,
        )


def test_gmgn_and_adapter_collection_do_not_invent_reserves() -> None:
    dataset = dataset_from_gmgn_candles(
        [Candle(time=1_762_819_200, close=Decimal("0.10"), volume=Decimal(9))],
        mint=USDC,
        symbol="USDC",
        dataset_id="gmgn-sample",
        name="GMGN sample",
        selection_note=NOTE,
        supplied=True,
    )
    assert dataset.bars[0].volume_quote == Decimal(9)
    assert dataset.bars[0].base_reserve is None
    assert dataset.bars[0].bid_size is None
    quote = adapt_observation(
        USDC,
        START,
        source="adapter",
        bid=Decimal("0.10"),
        ask=Decimal("0.11"),
        bid_size=Decimal(4),
        ask_size=Decimal(5),
        volume=Decimal(80),
        close=Decimal("0.10"),
    )
    from backtesting.pipeline import bar_from_quote

    bar = bar_from_quote(quote, symbol="USDC")
    assert bar.volume_quote == Decimal(80)
    assert bar.bid_size == Decimal(4)
    assert bar.ask_size == Decimal(5)
    assert bar.base_reserve is None
    quality = validate_quality(dataset, checked_at=START + timedelta(hours=2))
    assert quality.volume_only_bar_count == 1
    assert quality.fillable_bar_count == 0
    assert quality.stale is True


def test_quality_reports_gaps_outliers_and_real_depth() -> None:
    bars = (
        _bar(0, USDC, close=Decimal("1")),
        _bar(3, USDC, close=Decimal("1.1")),
        HistoricalBar(
            mint=USDC,
            symbol="USDC",
            observed_at=START + timedelta(minutes=4),
            source="supplied",
            high=Decimal("1"),
            low=Decimal("2"),
            close=Decimal("1.5"),
            base_reserve=Decimal(1000),
            quote_reserve=Decimal(1000),
        ),
    )
    report = validate_quality(
        _dataset(bars),
        checked_at=START + timedelta(minutes=4),
        expected_interval_seconds=60,
        stale_after_seconds=3600,
    )
    assert report.gap_count == 1
    assert report.outlier_count == 1
    assert report.reserve_bar_count == 1
    assert report.fillable_bar_count == 1
    assert report.stale is False
    assert report.live_trading_enabled is False
    assert "candle_volume_is_not_executable_depth" in report.limitations


def test_import_route_stores_quality_and_paper_mode_is_required(tmp_path: Path) -> None:
    secret = "local-test-token"
    settings = Settings(
        _env_file=None,
        log_dir=tmp_path,
        api_token=secret,
        execution_mode=ExecutionMode.PAPER,
    )
    app = create_app(settings)
    app.state.simulation_store = MemorySimulationStore()
    app.state.trading_store = MemoryTradingStore()
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {secret}"}
    csv_text = (
        "mint,symbol,observed_at,close,volume,base_reserve,quote_reserve\n"
        f"{USDC},USDC,2026-11-11T00:00:00+00:00,0.10,5,10000,1000\n"
        f"{USDC},USDC,2026-11-11T00:01:00+00:00,0.10,5,10000,1000\n"
        f"{USDC},USDC,2026-11-11T00:02:00+00:00,0.111,5,10000,1110\n"
    )
    imported = client.post(
        "/trading/simulation/imports",
        headers=headers,
        json={
            "dataset_id": "imported-bars",
            "name": "Imported bars",
            "selection_note": NOTE,
            "format": "csv",
            "content": csv_text,
        },
    )
    assert imported.status_code == 200
    body = imported.json()
    assert body["bars"] == 3
    assert body["fillable_bar_count"] == 3
    assert body["volume_only_bar_count"] == 0
    assert body["live_trading_enabled"] is False
    listed = client.get("/trading/simulation/datasets", headers=headers)
    assert listed.json()["datasets"][0]["dataset_id"] == "imported-bars"
    collected = client.post(
        "/trading/simulation/collections",
        headers=headers,
        json={
            "dataset_id": "gmgn-supplied",
            "name": "GMGN supplied",
            "selection_note": NOTE,
            "source": "gmgn_kline",
            "mint": USDC,
            "symbol": "USDC",
            "candles": [{"time": 1_762_819_200, "close": "0.10", "volume": "12"}],
        },
    )
    assert collected.status_code == 200
    assert collected.json()["volume_only_bar_count"] == 1
    assert collected.json()["fillable_bar_count"] == 0
    run = client.post(
        "/trading/simulation/backtests",
        headers=headers,
        json={
            "dataset_id": "imported-bars",
            "strategy": "momentum",
            "parameters": {"lookback": "2", "entry_return": "0.05", "stop_fraction": "0.10"},
            "starting_equity": "1000",
            "instruments": [
                {
                    "mint": USDC,
                    "symbol": "USDC",
                    "size_decimals": 2,
                    "price_decimals": 6,
                    "quote_symbol": "SOL",
                    "quote_decimals": 6,
                }
            ],
        },
    )
    assert run.status_code == 200
    report = run.json()
    assert report["parameters_deployed"] is False
    assert report["live_trading_enabled"] is False
    assert report["equity_curve"]
    assert "drawdown_curve" in report
    read_only = Settings(
        _env_file=None,
        log_dir=tmp_path,
        api_token=secret,
        execution_mode=ExecutionMode.READ_ONLY,
    )
    locked = TestClient(create_app(read_only))
    locked.app.state.simulation_store = MemorySimulationStore()  # type: ignore[attr-defined]
    locked.app.state.trading_store = MemoryTradingStore()  # type: ignore[attr-defined]
    refused = locked.post(
        "/trading/simulation/paper",
        headers=headers,
        json={
            "strategy_id": "momentum",
            "instrument": {
                "mint": USDC,
                "symbol": "USDC",
                "size_decimals": 2,
                "price_decimals": 6,
                "quote_symbol": "SOL",
                "quote_decimals": 6,
            },
            "side": "BUY",
            "quantity": "1",
            "idempotency_key": "manual-paper-1",
            "bar": {
                "mint": USDC,
                "symbol": "USDC",
                "observed_at": "2026-11-11T00:00:00+00:00",
                "source": "manual",
                "close": "0.10",
                "base_reserve": "10000",
                "quote_reserve": "1000",
            },
        },
    )
    assert refused.status_code == 403


def test_loopback_client_does_not_echo_the_token(tmp_path: Path) -> None:
    secret = "local-token-should-stay-hidden"
    settings = Settings(
        _env_file=None,
        log_dir=tmp_path,
        api_token=secret,
        api_port=1,
    )
    with pytest.raises(TradingValidationError) as caught:
        request_json(settings, "GET", "/trading/simulation/datasets")
    assert secret not in str(caught.value)
    assert "://" not in str(caught.value)


def _dataset(bars: tuple[HistoricalBar, ...]) -> HistoricalDataset:
    return HistoricalDataset(
        dataset_id="research-bars",
        name="Research bars",
        source="supplied",
        selection_note=NOTE,
        bars=bars,
        signals=(),
        members=(),
        limitations=(),
    )


def _bar(index: int, mint: str, close: Decimal | None = None) -> HistoricalBar:
    return HistoricalBar(
        mint=mint,
        symbol="USDC",
        observed_at=START + timedelta(minutes=index),
        source="supplied",
        close=close,
    )


def _mint(index: int) -> str:
    return ("1" * 31) + "23456"[index]
