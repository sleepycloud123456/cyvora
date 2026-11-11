"""JSON shapes for stored simulation reports. Decimals stay strings."""

from __future__ import annotations

from decimal import Decimal

from domain.simulation import (
    ExecutionAssumption,
    HistoricalBar,
    HistoricalDataset,
    HistoricalSignal,
    OrderSummary,
    PerformanceReport,
    SimulationReport,
    UniverseMember,
)


def dump_report(report: SimulationReport) -> dict[str, object]:
    """Serialize one report. ``parameters_deployed`` is written as false."""

    return {
        "run_id": report.run_id,
        "dataset_id": report.dataset_id,
        "kind": report.kind,
        "strategy_id": report.strategy_id,
        "created_at": report.created_at.isoformat(),
        "starting_equity": str(report.starting_equity),
        "ending_equity": _text(report.ending_equity),
        "performance": _performance(report.performance),
        "orders": [_order(item) for item in report.orders],
        "refusals": [
            {
                "mint": item.mint,
                "observed_at": item.observed_at.isoformat(),
                "side": item.side,
                "reason": item.reason,
            }
            for item in report.refusals
        ],
        "missing_tokens": list(report.missing_tokens),
        "limitations": list(report.limitations),
        "parameters_deployed": False,
        "windows": [
            {
                "train_started_at": item.train_started_at.isoformat(),
                "train_ended_at": item.train_ended_at.isoformat(),
                "test_started_at": item.test_started_at.isoformat(),
                "test_ended_at": item.test_ended_at.isoformat(),
                "selected_parameters": None
                if item.selected_parameters is None
                else dict(item.selected_parameters),
                "train_net_profit": _text(item.train_net_profit),
                "test_net_profit": _text(item.test_net_profit),
                "test_trade_count": item.test_trade_count,
                "selection_reason": item.selection_reason,
            }
            for item in report.windows
        ],
        "strategies": [
            {
                "strategy_id": item.strategy_id,
                "name": item.name,
                "net_profit": _text(item.net_profit),
                "trade_count": item.trade_count,
                "max_drawdown": _text(item.max_drawdown),
                "parameters": dict(item.parameters),
            }
            for item in report.strategies
        ],
    }


def dump_assumption(row: ExecutionAssumption) -> dict[str, object]:
    return {
        "client_order_id": row.client_order_id,
        "model": row.model,
        "impact": _text(row.impact),
        "fee_quote": str(row.fee_quote),
        "slippage_quote": str(row.slippage_quote),
        "delay_seconds": row.delay_seconds,
        "limitations": list(row.limitations),
        "simulated": True,
        "live_trading_enabled": False,
    }


def dataset_from_parts(
    *,
    dataset_id: str,
    name: str,
    source: str,
    selection_note: str,
    bars: tuple[HistoricalBar, ...],
    signals: tuple[HistoricalSignal, ...],
    members: tuple[UniverseMember, ...],
    limitations: tuple[str, ...],
) -> HistoricalDataset:
    return HistoricalDataset(
        dataset_id, name, source, selection_note, bars, signals, members, limitations
    )


def _performance(report: PerformanceReport) -> dict[str, object]:
    return {
        "total_return": _text(report.total_return),
        "net_profit": _text(report.net_profit),
        "gross_profit": str(report.gross_profit),
        "gross_loss": str(report.gross_loss),
        "win_rate": _text(report.win_rate),
        "average_win": _text(report.average_win),
        "average_loss": _text(report.average_loss),
        "profit_factor": _text(report.profit_factor),
        "max_drawdown": _text(report.max_drawdown),
        "sharpe": _text(report.sharpe),
        "sharpe_reason": report.sharpe_reason,
        "sortino": _text(report.sortino),
        "sortino_reason": report.sortino_reason,
        "average_holding_seconds": _text(report.average_holding_seconds),
        "trade_count": report.trade_count,
        "order_count": report.order_count,
        "exposure": _text(report.exposure),
        "fees": str(report.fees),
        "strategy_contribution": [
            {"strategy_id": name, "net_profit": str(value)}
            for name, value in report.strategy_contribution
        ],
        "risk_adjusted": _text(report.risk_adjusted),
        "limitations": list(report.limitations),
    }


def _order(order: OrderSummary) -> dict[str, object]:
    return {
        "client_order_id": order.client_order_id,
        "strategy_id": order.strategy_id,
        "mint": order.mint,
        "side": order.side,
        "state": order.state,
        "quantity": str(order.quantity),
        "filled_quantity": str(order.filled_quantity),
        "fill_price": _text(order.fill_price),
        "fee_quote": str(order.fee_quote),
        "slippage_quote": str(order.slippage_quote),
        "shield_decision": order.shield_decision,
        "reason": order.reason,
    }


def _text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)
