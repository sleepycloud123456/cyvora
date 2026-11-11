# Simulation

Date: 2026-11-11. Phase 6 is backtesting and a paper broker. Both are simulated. Shield remains the only approval authority. A paper approval does not enable a live order.

## What a fill is

A fill price comes from one of two explicit models:

| Model | When it is used | Price |
|---|---|---|
| `constant_product` | The bar has positive base and quote reserves | Constant-product average, worsened to the displayed ask or bid when that quote is worse |
| `displayed_depth` | The bar has a bid, an ask, and both sizes, and no reserve pair | One book level, capped at the participation fraction of the displayed size |

Candle close is a mark. It is not a fill. Candle volume is not copied into base size. A missing reserve pair does not become a zero-impact pool. A missing fee schedule is not a zero fee. The configured schedule can be an explicit zero, and the report says so.

For a buy, spending fraction `f` of the quote reserve has impact `f`. The broker caps the spend at the smaller of the participation fraction and the impact cap. For a sell, selling fraction `g` of the base reserve has impact `g / (1 + g)`. The sell size is capped by both the impact cap and the participation fraction.

The quote distance from the pre-trade spot or mid to that execution price is the slippage stored on the paper order. The gateway adds it to a buy and subtracts it from a sell. It does not calculate a second impact.

## Latency

A decision at time T may be priced only by an observation in `[T + delay, T + delay + max quote age]`. When the delay is zero, the decision bar's pool or book is used, not its close. A later bar is not visible to the strategy that made the decision. If no observation falls in the window, the order is refused and no fill is invented.

## Shield

Every priced paper order is submitted through `PaperExecutionGateway`, which calls Shield inside the ledger lock. The broker may choose a smaller quantity after Shield reports a size cap. Shield evaluates that smaller order again and can still deny it. A caller cannot set the decision. `paper_approved` means the local simulator may fill. `refuse_live_execution` still raises.

Stops, take-profits, and time exits are new paper orders. The planned stop is not the fill price. A gap fills at the later pool or book. Shield does not send the exit by itself.

Backtests use an isolated in-memory ledger. They do not change the operator's paper book. The paper route writes the operator's book and stores the cost-model assumption beside the order.

## Research limits

The report states the selection note supplied with the dataset. Mints listed in the universe and absent from the bars are missing. They are not priced. A walk-forward window selects parameters only from its train bars, using net profit and a minimum trade count. A window that does not qualify takes no test trades. Each window starts from the same paper equity. The selected parameters are stored on the report and `parameters_deployed` is false. Nothing copies them into a running strategy.

Sharpe and Sortino are per-bar ratios. They are omitted below 30 return observations, and Sharpe is omitted when the sample variance is zero. They are not annualized.

The strategies in this phase are momentum, breakout, and a follower for stored entry and exit signals. A signal is visible only at or before the decision time. These strategies do not read a wallet and do not submit a swap.

## Stored radar candles

`bar_from_radar_candle` copies a stored candle into a historical bar. Volume stays on `volume_quote`. Reserves are copied only when the stored snapshot is at or before the candle and both reserve fields were saved. A later snapshot is not copied onto an earlier candle. Importing those rows reads PostgreSQL. It does not call GMGN.

## What this phase does not do

- It does not sign, submit, or simulate a Solana transaction.
- It does not call a wallet, an RPC, or a GMGN trade route.
- It does not treat a Nautilus `BacktestEngine` fill as a CYVORA fill. That proof still cannot consult Shield.
- It does not deploy optimized parameters.
- It does not start Phase 7. Portfolio, Analytics, and the other unfinished terminal pages stay placeholders.
