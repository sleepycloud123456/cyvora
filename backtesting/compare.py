"""Run the same series through more than one strategy. Books stay separate."""

from __future__ import annotations

import uuid
from dataclasses import replace

from backtesting.engine import BASE_LIMITATIONS, BacktestSpec, SimulationStrategy, run_backtest
from backtesting.performance import measure
from domain.exceptions import TradingValidationError
from domain.simulation import SimulationReport, StrategySummary


def compare_strategies(
    spec: BacktestSpec, strategies: tuple[SimulationStrategy, ...]
) -> SimulationReport:
    """Score each strategy on its own paper book. No result is deployed."""

    if len(strategies) < 2 or len(strategies) > 3:
        raise TradingValidationError("A comparison needs two or three simulation strategies.")
    identifiers = {item.strategy_id for item in strategies}
    if len(identifiers) != len(strategies):
        raise TradingValidationError("Compared strategies need distinct ids.")
    reports = tuple(
        run_backtest(replace(spec, strategy=strategy, run_id="")) for strategy in strategies
    )
    summaries = tuple(
        StrategySummary(
            report.strategy_id,
            report.strategies[0].name if report.strategies else report.strategy_id,
            report.performance.net_profit,
            report.performance.trade_count,
            report.performance.max_drawdown,
            report.strategies[0].parameters if report.strategies else (),
        )
        for report in reports
    )
    performance = measure(
        orders=(),
        campaigns=(),
        strategy_id="comparison",
        starting_equity=spec.starting_equity,
        ending_equity=None,
        equity_curve=(),
        bars_in_market=0,
        bar_count=0,
    )
    performance = replace(
        performance,
        strategy_contribution=tuple(
            (item.strategy_id, item.net_profit) for item in summaries if item.net_profit is not None
        ),
        limitations=performance.limitations + ("strategies_are_not_one_portfolio",),
    )
    limitations = list(BASE_LIMITATIONS)
    limitations.append(
        "Each strategy used a separate paper book. Results are not a combined portfolio."
    )
    limitations.append("Optimized parameters are not deployed.")
    limitations.append(spec.dataset.selection_note)
    return SimulationReport(
        run_id=spec.run_id or f"run-{uuid.uuid4().hex[:12]}",
        dataset_id=spec.dataset.dataset_id,
        kind="comparison",
        strategy_id="comparison",
        created_at=spec.created_at,
        starting_equity=spec.starting_equity,
        ending_equity=None,
        performance=performance,
        orders=(),
        refusals=(),
        missing_tokens=reports[0].missing_tokens,
        limitations=tuple(dict.fromkeys(limitations)),
        parameters_deployed=False,
        windows=(),
        strategies=summaries,
    )
