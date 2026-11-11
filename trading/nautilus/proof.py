"""Local NautilusTrader 1.231.0 proof. Nothing in this module opens a socket.

The simulated venue is the Nautilus backtest engine. Its fills are evidence
of what that engine can represent. They are not CYVORA's paper ledger and
they are not Solana transactions.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from domain.trading import SolanaInstrument
from trading.nautilus.mapping import NAUTILUS_VERSION, project_instrument

_MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"


@dataclass(frozen=True)
class ProofOrder:
    """One engine result, recorded as text so the test can pin the 1.231.0 behavior."""

    label: str
    status: str
    filled: str
    average_price: str
    events: tuple[str, ...]


def installed_version() -> str:
    """Return the installed distribution version without reading the environment."""

    from importlib.metadata import version

    return version("nautilus-trader")


def proof_instrument() -> SolanaInstrument:
    return SolanaInstrument(
        mint=_MINT,
        symbol="BONK",
        size_decimals=6,
        price_decimals=9,
        quote_symbol="SOL",
        quote_decimals=9,
    )


def run_proof_orders() -> tuple[ProofOrder, ...]:
    """Run three offline cases: a full fill, an IOC partial, and a denied buy."""

    warnings.filterwarnings("ignore", message="Timestamp.utcnow is deprecated")
    if installed_version() != NAUTILUS_VERSION:
        raise RuntimeError("The Nautilus proof is pinned to 1.231.0.")
    projection, pair = project_instrument(proof_instrument())
    if pair is None or projection.instrument_id is None:
        raise RuntimeError("The proof instrument is outside Nautilus precision.")
    nautilus_pair: Any = pair
    return (
        _run(
            "full",
            nautilus_pair,
            balance="10 SOL",
            quantity="10.000000",
            time_in_force="GTC",
            consume=False,
            ask="100.000000",
        ),
        _run(
            "partial",
            nautilus_pair,
            balance="10 SOL",
            quantity="10.000000",
            time_in_force="IOC",
            consume=True,
            ask="5.000000",
        ),
        _run(
            "denied",
            nautilus_pair,
            balance="0.000000001 SOL",
            quantity="10.000000",
            time_in_force="GTC",
            consume=False,
            ask="100.000000",
        ),
    )


def _run(
    label: str,
    pair: Any,
    *,
    balance: str,
    quantity: str,
    time_in_force: str,
    consume: bool,
    ask: str,
) -> ProofOrder:
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.config import BacktestEngineConfig, LoggingConfig, StrategyConfig
    from nautilus_trader.model.data import QuoteTick
    from nautilus_trader.model.enums import (
        AccountType,
        BookType,
        OmsType,
        OrderSide,
        OrderStatus,
        TimeInForce,
    )
    from nautilus_trader.model.identifiers import Venue
    from nautilus_trader.model.objects import Money, Price, Quantity
    from nautilus_trader.trading.strategy import Strategy

    class Config(StrategyConfig, frozen=True):
        instrument_id: str
        order_qty: str
        time_in_force: str

    class ProofStrategy(Strategy):
        def __init__(self, config: Config) -> None:
            super().__init__(config)

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
                order_side=OrderSide.BUY,
                quantity=Quantity.from_str(self.config.order_qty),
                time_in_force=TimeInForce[self.config.time_in_force],
            )
            self.submit_order(order)

    engine = BacktestEngine(config=BacktestEngineConfig(logging=LoggingConfig(log_level="OFF")))
    try:
        venue = Venue("SOLANA")
        engine.add_venue(
            venue=venue,
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            starting_balances=[Money.from_str(balance)],
            book_type=BookType.L1_MBP,
            liquidity_consumption=consume,
        )
        engine.add_instrument(pair)
        stamp = 1_700_000_000_000_000_000
        engine.add_data(
            [
                QuoteTick(
                    pair.id,
                    Price.from_str("0.000000100"),
                    Price.from_str("0.000000101"),
                    Quantity.from_str("1000.000000"),
                    Quantity.from_str(ask),
                    stamp,
                    stamp,
                )
            ]
        )
        engine.add_strategy(
            ProofStrategy(
                Config(
                    instrument_id=str(pair.id),
                    order_qty=quantity,
                    time_in_force=time_in_force,
                )
            )
        )
        engine.run()
        orders = engine.cache.orders()
        if len(orders) != 1:
            raise RuntimeError("The Nautilus proof expected one simulated order.")
        order = orders[0]
        status = order.status
        status_name = status.name if hasattr(status, "name") else OrderStatus(status).name
        average = order.avg_px
        average_text = "none" if average is None else str(Decimal(str(average)))
        return ProofOrder(
            label=label,
            status=str(status_name),
            filled=str(order.filled_qty),
            average_price=average_text,
            events=tuple(type(event).__name__ for event in order.events),
        )
    finally:
        engine.dispose()
