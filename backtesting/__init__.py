"""Simulation-only backtests and the paper broker. Live trading is not started here."""

from backtesting.compare import compare_strategies
from backtesting.engine import run_backtest
from backtesting.walkforward import walk_forward

__all__ = ["compare_strategies", "run_backtest", "walk_forward"]
