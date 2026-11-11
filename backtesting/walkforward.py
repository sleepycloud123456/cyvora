"""Walk-forward splits. The test window does not choose the parameters."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from backtesting.engine import BacktestSpec, SimulationStrategy, run_backtest
from backtesting.history import HistoricalSeries
from backtesting.performance import measure
from domain.exceptions import TradingValidationError
from domain.simulation import SimulationReport, WindowResult

_MAX_WINDOWS = 12
_MAX_GRID = 20


def walk_forward(
    spec: BacktestSpec,
    grid: tuple[Mapping[str, str], ...],
    *,
    train_bars: int,
    test_bars: int,
    min_train_trades: int,
) -> SimulationReport:
    """Select on each train window and score only the following test window.

    The selected parameters are reported. They are not written to a live profile.
    """

    if not grid or len(grid) > _MAX_GRID:
        raise TradingValidationError("A walk-forward grid must contain 1 to 20 parameter sets.")
    if train_bars < 2 or test_bars < 1:
        raise TradingValidationError("Walk-forward needs at least 2 train bars and 1 test bar.")
    if min_train_trades < 1:
        raise TradingValidationError("Walk-forward selection requires at least one train trade.")
    series = HistoricalSeries(spec.dataset)
    stamps = series.timestamps
    windows: list[WindowResult] = []
    start = 0
    while start + train_bars + test_bars <= len(stamps):
        if len(windows) >= _MAX_WINDOWS:
            raise TradingValidationError("A walk-forward run can cover at most 12 windows.")
        train_times = stamps[start : start + train_bars]
        test_times = stamps[start + train_bars : start + train_bars + test_bars]
        selected, train_net, reason = _select(
            spec, grid, train_times[0], train_times[-1], min_train_trades
        )
        test_net = None
        test_trades = 0
        if selected is not None:
            chosen = spec.strategy.with_parameters(dict(selected))
            report = run_backtest(_child(spec, chosen, test_times[0], test_times[-1]))
            test_net = report.performance.net_profit
            test_trades = report.performance.trade_count
        windows.append(
            WindowResult(
                train_times[0],
                train_times[-1],
                test_times[0],
                test_times[-1],
                selected,
                train_net,
                test_net,
                test_trades,
                reason,
            )
        )
        start += test_bars
    if not windows:
        raise TradingValidationError(
            "The series is shorter than one train window plus one test window."
        )
    return _assemble(spec, tuple(windows))


def _select(
    spec: BacktestSpec,
    grid: tuple[Mapping[str, str], ...],
    start: datetime,
    end: datetime,
    min_trades: int,
) -> tuple[tuple[tuple[str, str], ...] | None, Decimal | None, str]:
    best: tuple[tuple[str, str], ...] | None = None
    best_net: Decimal | None = None
    for parameters in grid:
        strategy = spec.strategy.with_parameters(parameters)
        report = run_backtest(_child(spec, strategy, start, end))
        trades = report.performance.trade_count
        net = report.performance.net_profit
        if trades < min_trades or net is None:
            continue
        if best_net is None or net > best_net:
            best = strategy.parameter_pairs()
            best_net = net
    if best is None:
        return None, None, "no_parameter_met_the_train_rule"
    return best, best_net, "selected_on_train_net_profit"


def _child(
    spec: BacktestSpec,
    strategy: SimulationStrategy,
    start: datetime,
    end: datetime,
) -> BacktestSpec:
    series = HistoricalSeries(spec.dataset)
    return BacktestSpec(
        dataset=series.slice_between(start, end),
        strategy=strategy,
        instruments=spec.instruments,
        starting_equity=spec.starting_equity,
        schedule=spec.schedule,
        latency=spec.latency,
        participation=spec.participation,
        impact_cap=spec.impact_cap,
        created_at=spec.created_at,
        run_id="",
    )


def _assemble(spec: BacktestSpec, windows: tuple[WindowResult, ...]) -> SimulationReport:
    performance = measure(
        orders=(),
        campaigns=(),
        strategy_id=spec.strategy.strategy_id,
        starting_equity=spec.starting_equity,
        ending_equity=None,
        equity_curve=(),
        bars_in_market=0,
        bar_count=0,
    )
    limitations = [
        "Walk-forward parameters were selected on the train window only.",
        "Optimized parameters are not deployed.",
        "Each window starts from the same paper equity. Windows are not one portfolio.",
        "Test results are not one continuous portfolio.",
        spec.dataset.selection_note,
    ]
    if any(item.selected_parameters is None for item in windows):
        limitations.append("A window with no qualified train result took no test trades.")
    return SimulationReport(
        run_id=spec.run_id or f"run-{uuid.uuid4().hex[:12]}",
        dataset_id=spec.dataset.dataset_id,
        kind="walk_forward",
        strategy_id=spec.strategy.strategy_id,
        created_at=spec.created_at,
        starting_equity=spec.starting_equity,
        ending_equity=None,
        performance=performance,
        orders=(),
        refusals=(),
        missing_tokens=(),
        limitations=tuple(limitations),
        parameters_deployed=False,
        windows=windows,
        strategies=(),
    )
