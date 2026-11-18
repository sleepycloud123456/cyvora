"""The paper strategy runner stays inside Shield, limits, and the audit log."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from backtesting.memory_store import MemorySimulationStore
from config.settings import Settings
from domain.enums import ExecutionMode
from domain.shield import PAPER_APPROVED
from domain.simulation import HistoricalBar, HistoricalDataset, UniverseMember
from domain.trading import OrderSide, StrategyAudit, StrategyState
from operations.assembly import default_workers
from trading.execution.gateway import PaperExecutionGateway
from trading.memory_store import MemoryTradingStore
from trading.strategies.audit import MemoryAuditLog
from trading.strategies.manager import StrategyManager
from trading.strategies.runner import EvaluationSummary, evaluate_running_strategies

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
NOTE = "Tokens supplied for this research run, including those with no bars."
START = datetime(2026, 11, 11, tzinfo=UTC)


def test_runner_submits_through_shield_when_the_threshold_is_met() -> None:
    store, datasets, audits = _world()
    summary = evaluate_running_strategies(
        mode=ExecutionMode.PAPER,
        store=store,
        datasets=datasets,
        audits=audits,
        threshold="0.05",
        now=START + timedelta(minutes=2),
        entries_blocked=lambda: False,
    )
    assert summary.submitted == 1
    order = store.list_orders()[0]
    assert order.shield_decision == PAPER_APPROVED
    assert order.side is OrderSide.BUY
    assert order.fill_price is not None
    assert order.fill_price != Decimal("0.111")
    assert order.simulated is True
    assert audits.rows[-1].action == "submitted"
    assert audits.rows[-1].live_trading_enabled is False
    assert audits.rows[-1].threshold is not None
    store.positions.clear()
    again = evaluate_running_strategies(
        mode=ExecutionMode.PAPER,
        store=store,
        datasets=datasets,
        audits=audits,
        threshold="0.05",
        now=START + timedelta(minutes=2),
        entries_blocked=lambda: False,
    )
    assert again.submitted == 0
    assert len(store.list_orders()) == 1
    assert audits.rows[-1].action == "duplicate"


def test_threshold_size_rate_volume_and_kill_switch_block_orders() -> None:
    store, datasets, audits = _world()
    below = _evaluate(store, datasets, audits, threshold="0.90")
    assert below.submitted == 0
    assert audits.rows[-1].reason == "below_signal_threshold"
    assert store.list_orders() == ()

    missing_store, missing_data, _missing_audits = _world()
    missing_log = MemoryAuditLog()
    missing = _evaluate(missing_store, missing_data, missing_log, threshold=None)
    assert missing.submitted == 0
    assert missing_log.rows[-1].reason == "signal_threshold_not_configured"

    sized_store, sized_data, sized_log = _world()
    _retarget(sized_store, max_base_quantity="1")
    sized = _evaluate(sized_store, sized_data, sized_log, threshold="0.05")
    assert sized.refused == 1
    assert sized_log.rows[-1].reason == "size_limit"
    assert sized_store.list_orders() == ()

    limited_store, limited_data, limited_log = _world()
    _retarget(limited_store, max_orders="1")
    limited_log.append(_submitted(START + timedelta(minutes=2)))
    limited = _evaluate(limited_store, limited_data, limited_log, threshold="0.05")
    assert limited.skipped == 1
    assert limited_log.rows[-1].reason == "rate_limit"
    assert limited_store.list_orders() == ()

    volume_store, _volume_data, _volume_audits = _world()
    volume = MemorySimulationStore()
    volume.save_dataset(_dataset(_volume_bars()), START)
    volume_log = MemoryAuditLog()
    refused = _evaluate(volume_store, volume, volume_log, threshold="0.05")
    assert refused.refused == 1
    assert volume_log.rows[-1].reason == "candle_is_not_a_fill"
    assert volume_store.list_orders() == ()

    blocked_store, blocked_data, blocked_log = _world()
    blocked = evaluate_running_strategies(
        mode=ExecutionMode.PAPER,
        store=blocked_store,
        datasets=blocked_data,
        audits=blocked_log,
        threshold="0.05",
        now=START + timedelta(minutes=2),
        entries_blocked=lambda: True,
    )
    assert blocked.refused == 1
    assert blocked_log.rows[-1].action == "blocked"
    assert blocked_log.rows[-1].reason == "entries_blocked"
    assert blocked_store.list_orders() == ()


def test_read_only_supervisor_does_not_evaluate_orders(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, log_dir=tmp_path, execution_mode=ExecutionMode.READ_ONLY)
    worker = default_workers(settings, allow_radar_network=False)[-1]
    assert worker.kind == "paper_strategy"
    result = worker.tick(START)
    assert result.status == "skipped"
    assert "Live trading stays locked" in result.detail
    paper = Settings(_env_file=None, log_dir=tmp_path, execution_mode=ExecutionMode.PAPER)
    idle = default_workers(paper, allow_radar_network=False)[-1]
    waiting = idle.tick(START)
    assert waiting.status == "not_configured"
    assert "No order was submitted" in waiting.detail


def _world() -> tuple[MemoryTradingStore, MemorySimulationStore, MemoryAuditLog]:
    store = MemoryTradingStore()
    now = START
    gateway = PaperExecutionGateway(ExecutionMode.PAPER, store, lambda: now)
    manager = StrategyManager(ExecutionMode.PAPER, store, gateway, lambda: now)
    manager.register("momentum", "Momentum", _parameters())
    manager.start("momentum")
    assert store.get_strategy("momentum") is not None
    assert store.get_strategy("momentum").state is StrategyState.RUNNING  # type: ignore[union-attr]
    datasets = MemorySimulationStore()
    datasets.save_dataset(_dataset(_pool_bars()), START)
    return store, datasets, MemoryAuditLog()


def _retarget(store: MemoryTradingStore, **updates: str) -> None:
    current = store.get_strategy("momentum")
    assert current is not None
    parameters = dict(current.parameters)
    parameters.update(updates)
    manager = StrategyManager(
        ExecutionMode.PAPER,
        store,
        PaperExecutionGateway(ExecutionMode.PAPER, store, lambda: START),
        lambda: START,
    )
    store.strategies["momentum"] = current.__class__(
        strategy_id=current.strategy_id,
        name=current.name,
        state=current.state,
        parameters=tuple(sorted(parameters.items())),
        registered_at=current.registered_at,
        updated_at=current.updated_at,
    )
    del manager


def _parameters() -> dict[str, str]:
    return {
        "dataset_id": "research-bars",
        "mint": USDC,
        "symbol": "USDC",
        "model": "momentum",
        "quantity": "10",
        "size_decimals": "2",
        "price_decimals": "6",
        "quote_symbol": "SOL",
        "quote_decimals": "6",
        "equity_quote": "1000",
        "sol_balance": "1000",
        "lookback": "2",
        "entry_return": "0.05",
        "stop_fraction": "0.10",
    }


def _evaluate(
    store: MemoryTradingStore,
    datasets: MemorySimulationStore,
    audits: MemoryAuditLog,
    *,
    threshold: str | None,
) -> EvaluationSummary:
    return evaluate_running_strategies(
        mode=ExecutionMode.PAPER,
        store=store,
        datasets=datasets,
        audits=audits,
        threshold=threshold,
        now=START + timedelta(minutes=2),
        entries_blocked=lambda: False,
    )


def _submitted(moment: datetime) -> StrategyAudit:
    return StrategyAudit(
        strategy_id="momentum",
        action="submitted",
        reason="shield_path",
        signal_strength="0.11",
        threshold="0.05",
        client_order_id="paper-existing",
        created_at=moment,
        live_trading_enabled=False,
    )


def _dataset(bars: tuple[HistoricalBar, ...]) -> HistoricalDataset:
    return HistoricalDataset(
        dataset_id="research-bars",
        name="Research bars",
        source="supplied",
        selection_note=NOTE,
        bars=bars,
        signals=(),
        members=(UniverseMember(USDC, True, "Supplied for the research run."),),
        limitations=(),
    )


def _pool_bars() -> tuple[HistoricalBar, ...]:
    return (
        _pool(0, Decimal(1000), Decimal("0.10")),
        _pool(1, Decimal(1000), Decimal("0.10")),
        _pool(2, Decimal(1110), Decimal("0.111")),
    )


def _volume_bars() -> tuple[HistoricalBar, ...]:
    return tuple(
        HistoricalBar(
            mint=USDC,
            symbol="USDC",
            observed_at=START + timedelta(minutes=index),
            source="supplied",
            close=close,
            volume_quote=Decimal(5),
            security="clear",
            creator="Desk",
        )
        for index, close in enumerate((Decimal("0.10"), Decimal("0.10"), Decimal("0.111")))
    )


def _pool(index: int, quote: Decimal, close: Decimal) -> HistoricalBar:
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
