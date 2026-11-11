"""Phase 6 simulation. These tests cannot submit a chain transaction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backtesting.broker import BrokerCommand, PaperBroker, probe_quantity
from backtesting.compare import compare_strategies
from backtesting.costs import fee_quote
from backtesting.engine import BacktestSpec, run_backtest
from backtesting.fills import price_order
from backtesting.history import bar_from_radar_candle
from backtesting.liquidity import buy_fill, max_buy_base
from backtesting.performance import measure
from backtesting.strategies import BreakoutStrategy, MomentumStrategy
from backtesting.walkforward import walk_forward
from domain.enums import ExecutionMode
from domain.exceptions import TradingDisabled, TradingValidationError
from domain.shield import PAPER_APPROVED
from domain.simulation import (
    FeeSchedule,
    HistoricalBar,
    HistoricalDataset,
    LatencyModel,
    UniverseMember,
)
from domain.trading import LIVE_ORDER_STATES, OrderSide, OrderState, SolanaInstrument
from trading.execution.gateway import refuse_live_execution
from trading.memory_store import MemoryTradingStore

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
WSOL = "So11111111111111111111111111111111111111112"
START = datetime(2026, 11, 11, tzinfo=UTC)
NOTE = "Tokens supplied for this research run, including those with no bars."


def test_pool_impact_matches_quote_spent_and_a_candle_is_not_a_fill() -> None:
    quantity = max_buy_base(Decimal(10000), Decimal(1000), Decimal(20))
    bought = buy_fill(Decimal(10000), Decimal(1000), quantity)
    assert bought is not None
    assert bought.average_price > bought.spot_price
    assert bought.impact.quantize(Decimal("0.00000001")) == Decimal("0.02000000")
    candle = _bar(0, close=Decimal("0.20"))
    plan = price_order(
        candle,
        OrderSide.BUY,
        Decimal(10),
        _instrument(),
        _schedule(),
        participation=Decimal("0.02"),
        impact_cap=Decimal("0.02"),
    )
    assert plan.priced is False
    assert plan.reason == "candle_is_not_a_fill"
    assert plan.impact is None
    assert plan.reference_price is None


def test_backtest_fills_through_shield_at_the_pool_not_the_close() -> None:
    report = run_backtest(_spec(_rising()))
    filled = [item for item in report.orders if item.filled_quantity > 0]
    assert filled
    buy = filled[0]
    assert buy.shield_decision == PAPER_APPROVED
    assert buy.state == OrderState.CONFIRMED.value
    assert buy.fill_price is not None
    assert buy.fill_price != Decimal("0.111")
    assert buy.slippage_quote > 0
    assert buy.fee_quote > 0
    assert report.parameters_deployed is False
    assert "A missing pool impact is not treated as zero." in report.limitations
    assert WSOL in report.missing_tokens
    assert OrderState.SUBMITTED.value in {item.value for item in LIVE_ORDER_STATES}


def test_delay_uses_the_later_pool_and_not_the_signal_close() -> None:
    bars = _rising_bars() + (_pool_bar(3, Decimal(2000), Decimal("0.20")),)
    spec = _spec(
        _dataset(bars),
        latency=LatencyModel(60, 120),
    )
    report = run_backtest(spec)
    filled = [item for item in report.orders if item.side == "BUY" and item.filled_quantity > 0]
    assert filled
    assert filled[0].fill_price is not None
    assert filled[0].fill_price > Decimal("0.20")
    assert filled[0].fill_price != Decimal("0.111")


def test_stop_fill_is_not_the_planned_stop() -> None:
    bars = _rising_bars() + (_pool_bar(3, Decimal(500), Decimal("0.05")),)
    report = run_backtest(_spec(_dataset(bars)))
    sells = [item for item in report.orders if item.side == "SELL" and item.filled_quantity > 0]
    assert sells
    assert sells[0].fill_price is not None
    assert sells[0].fill_price < Decimal("0.06")
    assert "A planned stop is not a guaranteed exit." in report.limitations


def test_walk_forward_does_not_trade_a_test_only_pattern() -> None:
    bars = tuple(_pool_bar(index, Decimal(1000), Decimal("0.10")) for index in range(4))
    bars += (
        _pool_bar(4, Decimal(1200), Decimal("0.12")),
        _pool_bar(5, Decimal(1300), Decimal("0.13")),
    )
    spec = _spec(
        _dataset(bars), strategy=MomentumStrategy(lookback=1, entry_return=Decimal("0.01"))
    )
    report = walk_forward(
        spec,
        ({"entry_return": "0.01"}, {"entry_return": "0.50"}),
        train_bars=4,
        test_bars=2,
        min_train_trades=1,
    )
    assert report.parameters_deployed is False
    assert report.windows
    assert report.windows[0].selected_parameters is None
    assert report.windows[0].test_trade_count == 0
    assert report.windows[0].selection_reason == "no_parameter_met_the_train_rule"


def test_comparison_keeps_separate_books_and_does_not_deploy() -> None:
    report = compare_strategies(
        _spec(_rising()),
        (MomentumStrategy(), BreakoutStrategy()),
    )
    assert report.kind == "comparison"
    assert report.parameters_deployed is False
    assert {item.strategy_id for item in report.strategies} == {"momentum", "breakout"}
    assert "strategies_are_not_one_portfolio" in report.performance.limitations


def test_sharpe_is_withheld_until_the_sample_is_large_enough() -> None:
    short = measure(
        orders=(),
        campaigns=(),
        strategy_id="momentum",
        starting_equity=Decimal(1000),
        ending_equity=Decimal(1000),
        equity_curve=tuple(Decimal(1000) + index for index in range(10)),
        bars_in_market=0,
        bar_count=10,
    )
    assert short.sharpe is None
    assert short.sharpe_reason == "not_statistically_meaningful"
    safe = tuple(Decimal(1000) + Decimal(index % 3) for index in range(40))
    long = measure(
        orders=(),
        campaigns=(),
        strategy_id="momentum",
        starting_equity=safe[0],
        ending_equity=safe[-1],
        equity_curve=safe,
        bars_in_market=0,
        bar_count=40,
    )
    assert long.sharpe is not None
    assert long.sharpe_reason is None


def test_read_only_and_live_submission_stay_refused() -> None:
    with pytest.raises(TradingDisabled, match="Read-only"):
        run_backtest(_spec(_rising()), mode=ExecutionMode.READ_ONLY)
    with pytest.raises(TradingDisabled, match="Live execution is disabled"):
        refuse_live_execution("submit_swap")
    store = MemoryTradingStore()
    broker = PaperBroker(
        ExecutionMode.READ_ONLY,
        store,
        _clock,
        _schedule(),
        LatencyModel(0, 60),
        participation=Decimal("0.02"),
        impact_cap=Decimal("0.02"),
    )
    with pytest.raises(TradingDisabled):
        broker.execute(_command())


def _clock() -> datetime:
    return START


def test_radar_candle_volume_is_not_base_size_and_future_reserves_are_dropped() -> None:
    later = START + timedelta(minutes=5)
    bar, notes = bar_from_radar_candle(
        mint=USDC,
        symbol="USDC",
        candle_time=int(START.timestamp()),
        open_price=Decimal("0.1"),
        high=Decimal("0.2"),
        low=Decimal("0.1"),
        close=Decimal("0.2"),
        volume=Decimal(50),
        evidence=(("base_reserve", "10"), ("quote_reserve", "10")),
        snapshot_at=later,
    )
    assert bar is not None
    assert bar.base_volume is None
    assert bar.volume_quote == Decimal(50)
    assert bar.base_reserve is None
    assert bar.quote_reserve is None
    assert "gmgn_candle_volume_is_not_base_size" in notes
    assert "radar_liquidity_is_not_a_reserve_pair" in notes


def test_fee_schedule_is_explicit() -> None:
    amount = fee_quote(_schedule(), Decimal(100), 6)
    assert amount == Decimal("0.100000")
    with pytest.raises(TradingValidationError):
        fee_quote(FeeSchedule("paper_fee", Decimal(-1), Decimal(0)), Decimal(1), 6)


def _spec(
    dataset: HistoricalDataset,
    *,
    strategy: MomentumStrategy | BreakoutStrategy | None = None,
    latency: LatencyModel | None = None,
) -> BacktestSpec:
    return BacktestSpec(
        dataset=dataset,
        strategy=strategy or MomentumStrategy(lookback=2, entry_return=Decimal("0.05")),
        instruments={USDC: _instrument()},
        starting_equity=Decimal(1000),
        schedule=_schedule(),
        latency=latency or LatencyModel(0, 120),
        participation=Decimal("0.02"),
        impact_cap=Decimal("0.02"),
        created_at=START,
        run_id="run-test",
    )


def _rising() -> HistoricalDataset:
    return _dataset(_rising_bars())


def _rising_bars() -> tuple[HistoricalBar, ...]:
    return (
        _pool_bar(0, Decimal(1000), Decimal("0.10")),
        _pool_bar(1, Decimal(1000), Decimal("0.10")),
        _pool_bar(2, Decimal(1110), Decimal("0.111")),
    )


def _dataset(bars: tuple[HistoricalBar, ...]) -> HistoricalDataset:
    return HistoricalDataset(
        dataset_id="research-bars",
        name="Research bars",
        source="supplied",
        selection_note=NOTE,
        bars=bars,
        signals=(),
        members=(
            UniverseMember(USDC, True, "Supplied for the research run."),
            UniverseMember(WSOL, True, "Listed in the universe and absent from the bars."),
        ),
        limitations=(),
    )


def _pool_bar(index: int, quote: Decimal, close: Decimal) -> HistoricalBar:
    return HistoricalBar(
        mint=USDC,
        symbol="USDC",
        observed_at=START + timedelta(minutes=index),
        source="supplied",
        close=close,
        base_reserve=Decimal(10000),
        quote_reserve=quote,
        security="clear",
        creator="Desk",
        volume_quote=Decimal(1),
    )


def _bar(index: int, close: Decimal) -> HistoricalBar:
    return HistoricalBar(
        mint=USDC,
        symbol="USDC",
        observed_at=START + timedelta(minutes=index),
        source="supplied",
        close=close,
    )


def _instrument() -> SolanaInstrument:
    return SolanaInstrument(USDC, "USDC", 2, 6, "SOL", 6)


def _schedule() -> FeeSchedule:
    return FeeSchedule("paper_fee", Decimal(0), Decimal("0.001"))


def _command() -> BrokerCommand:
    return BrokerCommand(
        strategy_id="momentum",
        instrument=_instrument(),
        side=OrderSide.BUY,
        quantity=probe_quantity(),
        bar=_pool_bar(0, Decimal(1000), Decimal("0.10")),
        exit_kind="entry",
        stop_fraction=Decimal("0.10"),
        signal_ref=None,
        idempotency_key="bt-buy-0001",
        narrative="momentum",
        equity_quote=Decimal(1000),
        sol_balance=Decimal(1000),
        marks=(),
    )
