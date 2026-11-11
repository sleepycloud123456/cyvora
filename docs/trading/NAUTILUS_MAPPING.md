# NautilusTrader mapping

Date: 2026-11-11. Package: `nautilus_trader` 1.231.0. Wheel: `nautilus_trader-1.231.0-cp313-cp313-win_amd64.whl`. Interpreter: the project CPython 3.13.18. PyPI's newest stable release on this date is still 1.231.0. `2.0.0` final is not published. `2.0.0rc3` through `2.0.0rc9` stay unused.

The import and the three backtest cases below ran on this Windows 11 Home machine. Nautilus documents Windows Server 2022 as the CI host. This PC is not that host. The wheel imported and the local engine ran.

## What CYVORA uses Nautilus for

`trading/nautilus` builds Nautilus objects and runs `BacktestEngine` in process. It does not construct a `LiveExecutionClient` or a `LiveDataClient`, and it does not open a venue socket. The proof does not write the CYVORA paper ledger. PostgreSQL remains the system of record for paper orders.

A Nautilus market order is not a Solana swap. The engine's `FILLED` state is not a chain confirmation.

## Instrument

`CurrencyPair` is the 1.231.0 type that can hold a spot price and a size. The mapping is a synthetic pair:

| CYVORA field | Nautilus field |
|---|---|
| Mint | `InstrumentId` symbol and base `Currency.code`, venue `SOLANA` |
| Symbol | `info["symbol"]` only. It is not the instrument id, because two mints can share a ticker. |
| Size decimals | `size_precision` and base currency precision |
| Price decimals | `price_precision` and `price_increment` |
| Quote symbol and decimals | Quote `Currency` |
| Chain | `info["chain"] = "sol"` |
| Mapping label | `info["mapping"] = "synthetic_spot_pair"` |

`SOLANA` is a CYVORA venue label inside the backtest. Nautilus 1.231.0 does not ship a Solana or GMGN adapter.

`FIXED_PRECISION` on this wheel is 9. A price, size, or quote scale above 9 is not projected and is not rounded. Those orders still exist as CYVORA `Decimal` values, which allow 18 fractional digits in PostgreSQL.

A single-currency cash account rejects a `CurrencyPair`. The proof uses a multi-currency cash account with a SOL balance and no account base currency. Quantity text passed to Nautilus uses the instrument size precision. `1000` is precision 0 and does not match a size precision of 6.

## Market data

`trading/nautilus/data.py` builds a Nautilus object only when the contract already contains the required fields.

| Contract | Nautilus object | Required fields |
|---|---|---|
| Quote | `QuoteTick` | Bid, ask, bid size, and ask size |
| Trade | `TradeTick` | Last price, last size, and `size_is_base` |
| Bar | External `Bar`, price type `LAST` | Open, high, low, close, base size, and resolution `1m`, `5m`, `15m`, or `1h` |

A missing bid or ask stays missing. GMGN candle volume is copied onto the contract as volume and is not treated as a base size, so a candle does not become a trade or a bar. `integrations/solana` performs that adaptation. It does not open an RPC connection, inspect an account, or submit a transaction.

## Orders the engine actually produced

`trading/nautilus/proof.py` runs three offline cases against one synthetic BONK/SOL book. Bid `0.000000100`, ask `0.000000101`, order quantity 10. Timestamps are fixed. No network call is part of the proof.

| Case | Engine setup | Result on 1.231.0 |
|---|---|---|
| Full | GTC, ask size 100, liquidity consumption off, 10 SOL cash | `FILLED`, filled `10.000000`, one `OrderFilled` |
| Partial | IOC, ask size 5, liquidity consumption on, 10 SOL cash | `CANCELED`, filled `5.000000`, then `OrderCanceled` |
| Denied | GTC, ask size 100, cash `0.000000001` SOL | `DENIED`, filled `0.000000`, `OrderDenied` |

The event list also contains `OrderInitialized` and `OrderSubmitted` before a fill or a denial. `OrderSubmitted` here means the backtest matching engine accepted the order object. It does not mean a transaction was signed.

Nautilus order statuses include `PARTIALLY_FILLED`, `FILLED`, `CANCELED`, `DENIED`, and `REJECTED`. They do not include CYVORA's `SIMULATION_PENDING`, `CONFIRMATION_PENDING`, or `UNKNOWN`. Those remain CYVORA states. Paper code is not allowed to store `SUBMISSION_PENDING`, `SUBMITTED`, or `CONFIRMATION_PENDING`.

The earlier book-walk case, with GTC and liquidity consumption, filled 5 at the ask and 5 one tick worse. `order.slippage` was `0` for that run. CYVORA does not read `order.slippage` as a fill price. Paper slippage is a quote amount the caller supplies, added to a buy or subtracted from a sell. The paper path does not estimate pool impact. That model belongs to a later phase.

Nautilus maker and taker fields are percentages of notional on the instrument. The paper ledger records a caller-supplied quote fee instead. A fee of zero means the caller did not supply one.

## Paper ledger

`PaperExecutionGateway.submit` runs only when the mode is `PAPER`. `READ_ONLY` stores nothing. `refuse_live_execution` is the live entry and it always raises. A repeated idempotency key returns the stored order and does not apply a second fill.

A paper fill moves through `CREATED`, `VALIDATED`, `SIMULATION_PENDING`, `SIMULATION_PASSED`, and `CONFIRMED`. Rejected, failed, and insufficient-position sells stop at `FAILED` and do not change the position. `CONFIRMED` means the local simulator closed the order. It does not mean a Solana transaction was confirmed.

Reconciliation compares the stored order with a supplied report. A missing or conflicting report sets the order to `UNKNOWN`, leaves the position unchanged, and does not submit another order.

The strategy manager registers a slot, starts it only in paper mode, and routes an explicit intent. Every stored order has `shield_decision = not_authorized`. A request that claims Shield approval is refused. The API process sets `RUNNING` strategies back to `STOPPED` when it starts. The desktop shows the stored rows and does not start a strategy.

No signal strategy is implemented. Shield, the paper broker, and cost models are later phases.
