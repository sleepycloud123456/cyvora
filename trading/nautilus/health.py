"""Paper-only NautilusTrader health check.

The backtest node and engine run in process. They do not open a venue socket.
The operator paper book is still Shield plus the CYVORA simulator. This module
does not write that book and does not submit a transaction.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from backtesting.engine import BacktestSpec, run_backtest
from backtesting.strategies import MomentumStrategy
from domain.enums import ExecutionMode
from domain.exceptions import TradingDisabled
from domain.shield import PAPER_APPROVED, ExitKind, RiskIntent
from domain.simulation import (
    FeeSchedule,
    HistoricalBar,
    HistoricalDataset,
    LatencyModel,
    UniverseMember,
)
from domain.trading import OrderSide, OrderState, SimulationOutcome, SolanaInstrument
from trading.execution.gateway import PaperExecutionGateway, PaperOrderRequest
from trading.memory_store import MemoryTradingStore
from trading.nautilus.mapping import NAUTILUS_VERSION, project_instrument
from trading.nautilus.proof import installed_version, proof_instrument
from trading.portfolio.accounting import unrealized_pnl
from trading.strategies.manager import StrategyManager

_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
_NOW = datetime(2026, 11, 11, tzinfo=UTC)
_SLOT = "health-slot"


@dataclass(frozen=True)
class HealthCheck:
    """One step of the paper health run."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class NautilusHealthReport:
    """The checks from one local run. Nothing here is a live order."""

    version: str
    checks: tuple[HealthCheck, ...]

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.checks)


def run_nautilus_health() -> NautilusHealthReport:
    """Import Nautilus, exercise the paper core, and run a short stored-bar backtest."""

    warnings.filterwarnings("ignore", message="Timestamp.utcnow is deprecated")
    checks = (
        _guard("import", _import_version),
        _guard("backtest_node", _node_cycle),
        _guard("instrument_fill", _instrument_fill),
        _guard("shield_paper_book", _shield_paper_book),
        _guard("kill_switch", _kill_switch),
        _guard("stored_backtest", _stored_backtest),
    )
    return NautilusHealthReport(installed_version(), checks)


def _guard(name: str, func: Callable[[], HealthCheck]) -> HealthCheck:
    try:
        return func()
    except Exception as exc:
        text = str(exc).splitlines()[0][:180]
        if "://" in text:
            text = type(exc).__name__
        return HealthCheck(name, False, f"{type(exc).__name__}: {text}")


def _import_version() -> HealthCheck:
    import nautilus_trader
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.backtest.node import BacktestNode

    del nautilus_trader, BacktestEngine, BacktestNode
    found = installed_version()
    if found != NAUTILUS_VERSION:
        return HealthCheck("import", False, f"Installed {found}.")
    return HealthCheck("import", True, f"nautilus_trader {found} imports.")


def _node_cycle() -> HealthCheck:
    from nautilus_trader.backtest.config import (
        BacktestEngineConfig,
        BacktestRunConfig,
        BacktestVenueConfig,
    )
    from nautilus_trader.backtest.node import BacktestNode
    from nautilus_trader.config import LoggingConfig

    venue = BacktestVenueConfig(
        name="SOLANA",
        oms_type="NETTING",
        account_type="CASH",
        starting_balances=["10 SOL"],
        base_currency=None,
        book_type="L1_MBP",
    )
    node = BacktestNode(
        configs=[
            BacktestRunConfig(
                venues=[venue],
                data=[],
                engine=BacktestEngineConfig(logging=LoggingConfig(log_level="OFF")),
            )
        ]
    )
    try:
        results = node.run()
        if len(results) != 1:
            return HealthCheck("backtest_node", False, "The node did not return one run.")
    finally:
        node.dispose()
    leftover = [engine for engine in node.get_engines() if not engine.trader.is_disposed]
    if leftover:
        return HealthCheck("backtest_node", False, "An engine was still running after dispose.")
    return HealthCheck(
        "backtest_node",
        True,
        "BacktestNode ran one empty paper venue and disposed its engine.",
    )


def _instrument_fill() -> HealthCheck:
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.config import BacktestEngineConfig, LoggingConfig, StrategyConfig
    from nautilus_trader.model.data import QuoteTick
    from nautilus_trader.model.enums import AccountType, BookType, OmsType, TimeInForce
    from nautilus_trader.model.enums import OrderSide as NautilusSide
    from nautilus_trader.model.identifiers import Venue
    from nautilus_trader.model.objects import Money, Price, Quantity
    from nautilus_trader.trading.strategy import Strategy

    projection, pair = project_instrument(proof_instrument())
    if pair is None or projection.instrument_id is None:
        return HealthCheck("instrument_fill", False, "The proof instrument did not project.")
    nautilus_pair: Any = pair

    class Config(StrategyConfig, frozen=True):
        instrument_id: str

    class BuyOnce(Strategy):
        def on_start(self) -> None:
            from nautilus_trader.model.identifiers import InstrumentId

            self.subscribe_quote_ticks(InstrumentId.from_str(self.config.instrument_id))

        def on_quote_tick(self, tick: object) -> None:
            del tick
            if self.cache.orders():
                return
            from nautilus_trader.model.identifiers import InstrumentId

            order = self.order_factory.market(
                instrument_id=InstrumentId.from_str(self.config.instrument_id),
                order_side=NautilusSide.BUY,
                quantity=Quantity.from_str("10.000000"),
                time_in_force=TimeInForce.GTC,
            )
            self.submit_order(order)

    engine = BacktestEngine(config=BacktestEngineConfig(logging=LoggingConfig(log_level="OFF")))
    try:
        engine.add_venue(
            venue=Venue("SOLANA"),
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            starting_balances=[Money.from_str("10 SOL")],
            book_type=BookType.L1_MBP,
        )
        engine.add_instrument(nautilus_pair)
        if engine.cache.instrument(nautilus_pair.id) is None:
            return HealthCheck("instrument_fill", False, "The instrument was not in the cache.")
        stamp = 1_700_000_000_000_000_000
        engine.add_data(
            [
                QuoteTick(
                    nautilus_pair.id,
                    Price.from_str("0.000000100"),
                    Price.from_str("0.000000101"),
                    Quantity.from_str("1000.000000"),
                    Quantity.from_str("100.000000"),
                    stamp,
                    stamp,
                )
            ]
        )
        engine.add_strategy(BuyOnce(Config(instrument_id=str(nautilus_pair.id))))
        engine.run()
        orders = engine.cache.orders()
        opened = list(engine.cache.positions_open())
        if len(orders) != 1 or str(orders[0].filled_qty) != "10.000000":
            return HealthCheck("instrument_fill", False, "The paper order did not fill.")
        if len(opened) != 1 or str(opened[0].quantity) != "10.000000":
            return HealthCheck("instrument_fill", False, "The paper position was not opened.")
        return HealthCheck(
            "instrument_fill",
            True,
            "Loaded the synthetic BONK/SOL pair, filled 10, and opened one position.",
        )
    finally:
        engine.dispose()


def _shield_paper_book() -> HealthCheck:
    store = MemoryTradingStore()
    gateway = PaperExecutionGateway(ExecutionMode.PAPER, store, lambda: _NOW)
    manager = StrategyManager(ExecutionMode.PAPER, store, gateway, lambda: _NOW)
    manager.register(_SLOT, "Health slot")
    manager.start(_SLOT)
    buy = manager.submit(_SLOT, _request("health-buy", OrderSide.BUY, Decimal(4), Decimal(2)))
    sell = manager.submit(_SLOT, _request("health-sell", OrderSide.SELL, Decimal(4), Decimal(3)))
    position = store.positions[_MINT]
    if buy.shield_decision != PAPER_APPROVED or buy.state is not OrderState.CONFIRMED:
        return HealthCheck("shield_paper_book", False, "Shield did not confirm the paper buy.")
    if sell.state is not OrderState.CONFIRMED or position.realized_pnl_quote != Decimal(4):
        return HealthCheck("shield_paper_book", False, "The round trip did not realize 4.")
    if position.quantity != 0 or unrealized_pnl(position, Decimal(3)) != Decimal(0):
        return HealthCheck("shield_paper_book", False, "The position was not flat.")
    return HealthCheck(
        "shield_paper_book",
        True,
        "Shield approved a paper round trip. Realized PnL is 4 SOL. The book is in memory.",
    )


def _kill_switch() -> HealthCheck:
    store = MemoryTradingStore()

    def clock() -> datetime:
        return _NOW

    open_gateway = PaperExecutionGateway(ExecutionMode.PAPER, store, clock)
    manager = StrategyManager(ExecutionMode.PAPER, store, open_gateway, clock)
    manager.register(_SLOT, "Health slot")
    manager.start(_SLOT)
    first = manager.submit(_SLOT, _request("health-buy", OrderSide.BUY, Decimal(4), Decimal(2)))
    blocked = PaperExecutionGateway(ExecutionMode.PAPER, store, clock, entries_blocked=lambda: True)
    blocked_manager = StrategyManager(ExecutionMode.PAPER, store, blocked, clock)
    try:
        blocked_manager.submit(_SLOT, _request("health-new", OrderSide.BUY, Decimal(1), Decimal(2)))
    except TradingDisabled as exc:
        if "kill switch" not in str(exc):
            return HealthCheck("kill_switch", False, "The refusal did not name the kill switch.")
    else:
        return HealthCheck("kill_switch", False, "A new paper order was stored while blocked.")
    if len(store.orders) != 1 or store.positions[_MINT].quantity != Decimal(4):
        return HealthCheck("kill_switch", False, "The blocked order changed the book.")
    replay = blocked_manager.submit(
        _SLOT, _request("health-buy", OrderSide.BUY, Decimal(4), Decimal(2))
    )
    if replay.client_order_id != first.client_order_id or len(store.orders) != 1:
        return HealthCheck("kill_switch", False, "A repeated key created a second order.")
    return HealthCheck(
        "kill_switch",
        True,
        "A new paper order was refused. The original order was returned for the same key.",
    )


def _stored_backtest() -> HealthCheck:
    report = run_backtest(_spec())
    filled = [item for item in report.orders if item.filled_quantity > 0]
    if not filled or filled[0].shield_decision != PAPER_APPROVED:
        return HealthCheck("stored_backtest", False, "The stored bars did not fill through Shield.")
    if report.parameters_deployed:
        return HealthCheck("stored_backtest", False, "The backtest deployed parameters.")
    return HealthCheck(
        "stored_backtest",
        True,
        "A three-bar stored series filled through Shield on an isolated paper ledger.",
    )


def _request(key: str, side: OrderSide, quantity: Decimal, price: Decimal) -> PaperOrderRequest:
    return PaperOrderRequest(
        strategy_id=_SLOT,
        instrument=SolanaInstrument(_MINT, "USDC", 6, 6, "SOL", 9),
        side=side,
        quantity=quantity,
        reference_price=price,
        outcome=SimulationOutcome.FILL,
        idempotency_key=key,
        risk=_intent(side, quantity, price),
    )


def _intent(side: OrderSide, quantity: Decimal, price: Decimal) -> RiskIntent:
    sell = side is OrderSide.SELL
    return RiskIntent(
        mint=_MINT,
        side=side.value,
        quantity=quantity,
        reference_price=price,
        fee_quote=Decimal(0),
        slippage_quote=Decimal(0),
        size_decimals=6,
        price_decimals=6,
        quote_decimals=9,
        quote_symbol="SOL",
        stop_price=None if sell else price / Decimal(2),
        equity_quote=None if sell else Decimal(10000),
        sol_balance=None if sell else Decimal(10000),
        valued_at=None if sell else _NOW,
        marks=(),
        liquidity_quote=None if sell else Decimal(100000),
        volatility=None,
        confidence=None,
        token_age_seconds=None,
        market_condition=None,
        security=None if sell else "clear",
        creator=None if sell else "DeskWallet",
        narrative=None if sell else "momentum",
        liquidity_provider=None,
        driver=None,
        estimated_impact=None,
        exit_kind=ExitKind.NORMAL.value if sell else ExitKind.ENTRY.value,
        signal_ref=None,
        emergency=None,
    )


def _spec() -> BacktestSpec:
    bars = tuple(
        HistoricalBar(
            mint=_MINT,
            symbol="USDC",
            observed_at=_NOW + timedelta(minutes=index),
            source="stored",
            close=close,
            base_reserve=Decimal(10000),
            quote_reserve=quote,
            security="clear",
            creator="Desk",
            volume_quote=Decimal(1),
        )
        for index, quote, close in (
            (0, Decimal(1000), Decimal("0.10")),
            (1, Decimal(1000), Decimal("0.10")),
            (2, Decimal(1110), Decimal("0.111")),
        )
    )
    dataset = HistoricalDataset(
        dataset_id="nautilus-health-bars",
        name="Health bars",
        source="stored",
        selection_note="Three stored bars for the Nautilus health check.",
        bars=bars,
        signals=(),
        members=(UniverseMember(_MINT, True, "Supplied for the health check."),),
        limitations=(),
    )
    return BacktestSpec(
        dataset=dataset,
        strategy=MomentumStrategy(lookback=2, entry_return=Decimal("0.05")),
        instruments={_MINT: SolanaInstrument(_MINT, "USDC", 6, 6, "SOL", 9)},
        starting_equity=Decimal(1000),
        schedule=FeeSchedule("paper_fee", Decimal(0), Decimal("0.001")),
        latency=LatencyModel(0, 120),
        participation=Decimal("0.02"),
        impact_cap=Decimal("0.02"),
        created_at=_NOW,
        run_id="nautilus-health",
    )


def main() -> None:
    """Print check names only. This does not print configuration."""

    report = run_nautilus_health()
    for item in report.checks:
        state = "ok" if item.passed else "failed"
        print(f"{item.name} {state}: {item.detail}")
    if not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
