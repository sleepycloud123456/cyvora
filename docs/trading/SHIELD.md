# CYVORA Shield

Shield is the only authority that can approve a paper order. A strategy, the desktop, an AI score, or a request field cannot approve itself. `paper_approved` means the local simulator may run. It does not enable a live order, a signer, or a swap.

The engine is deterministic. The same limits, book, intent, and clock produce the same decision. Quantities use `Decimal`. Sizes round down.

## What an approval is

| Decision | Meaning |
|---|---|
| `paper_approved` | The paper simulator may fill, partially fill, or reject the order. |
| `denied` | No simulation ran. The reason code is stored on the order. |
| `not_authorized` | Legacy Phase 4 rows only. New orders do not use it. |

`live_trading_enabled` on a Shield row is constrained to false. `refuse_live_execution` still raises. Settings still reject `LIVE`, `LIVE_LOCKED`, and `LIVE_AUTHORIZED`.

A caller that sets `shield_approved` is refused before a decision is stored.

## Initial limits

| Control | Initial value |
|---|---|
| Maximum deployed capital | 70% of verified equity |
| Minimum SOL reserve | 10% of verified equity |
| Planned risk per trade | 1% of verified equity |
| Daily loss | 5% of the UTC-day opening equity |
| Maximum drawdown | 15% from the high-water mark |
| Consecutive losing campaigns | 3 |
| Liquidity participation | 2% of supplied pool quote liquidity |
| Correlated cluster | 25% of verified equity |
| Supplied price impact | 2% when the caller supplies an impact |

Deployed capital and the SOL reserve must sum to at most 100%. Risk per trade cannot exceed the daily loss limit, and the daily loss limit cannot exceed maximum drawdown. A cluster cap cannot exceed the deployed cap. Take-profit quantity fractions must sum to at most 1, and the gains must increase. Invalid settings are rejected and the previous book is left in place.

The 70% and 10% caps are both applied. When verified equity is SOL plus marked token positions, the 70% cap is the tighter notional cap. The reserve cap binds when a configured deployed cap sits next to the reserve and the order fee makes the SOL spend tighter than the notional cap. Pending in-flight buys count toward deployed capital and are not also counted as a second copy of the position.

## Valuation

A new buy is denied unless the caller supplies a timezone-aware valuation time, a positive equity, and a SOL balance that together match:

`equity = SOL balance + sum(open quantity × supplied mark)`

A missing mark on an open position is unverified. Equity is not inferred from cost. A valuation older than the configured age (120 seconds by default) is stale. The quote for a new buy is SOL, because the reserve is a SOL reserve.

## Position size

Planned loss per unit is the distance from the expected paper fill to the effective stop, plus the caller-supplied fee per unit. The expected fill is the reference price plus the caller-supplied buy slippage. It is not a pool-impact price.

```text
risk budget = equity × risk per trade × confidence
quantity = risk budget / planned loss per unit
```

Confidence, when supplied, is in `(0, 1]` and can only reduce the budget. A missing confidence does not increase the size. The requested quantity is denied when it exceeds the smallest of the risk, deployed, reserve, liquidity, supplied-impact, and correlation caps. Shield does not silently resize the order. The decision includes the rounded-down quantity that would fit.

If volatility is supplied, the volatility stop is `fill − (volatility × multiplier)`, widened when supplied liquidity is thin relative to equity, when a supplied token age is inside the young-token window, or when the market condition is the explicit value `stressed`. Missing age, liquidity, or market condition is skipped. It is not replaced with a guess. The effective stop is the lower of the explicit stop and the volatility stop, so a tight stop cannot inflate the size past the volatility distance.

A planned stop is not a guaranteed exit. A gap or a liquidity collapse can make the realized loss larger than the planned loss. That sentence is stored on sizing decisions.

## Stops, take-profits, and trails

Default take-profit gains are 30%, 50%, 100%, and 200%. Each takes 25% of the filled quantity. Rounding down keeps the planned total at or below the position. A `take_profit` sell must reach a level and cannot sell more than that level's remaining plan.

A trailing stop activates after a 30% gain by default. It moves only upward, waits for the minimum interval between trail updates, and can step to the average price once the break-even gain is reached. Break-even may move inside the interval. A missing volatility is not invented; the fractional distance is used.

Shield does not submit the exit. A stop, trail, or take-profit becomes a paper order only when a caller submits one and Shield approves that reduce-only order. Automatic exit execution is not part of this phase.

## Daily loss, drawdown, and consecutive losses

The daily baseline is the verified equity on the first observation of a UTC date. Later observations the same day do not replace the opening equity. A restart loads the stored row.

Drawdown uses the stored high-water mark. The mark ratchets up when a higher verified equity is observed. A restart does not reset it.

A campaign runs from an entry to flat. Partial sells stay in that campaign. The net result, after fees already included in the paper ledger, counts once when the position is flat. A loss increments the streak. A gain resets it. A zero result does neither. The streak pauses new entries at the configured count.

When a limit is latched, new entries stay blocked after a restart. Reduce-only sells remain allowed. Shield does not liquidate open positions because a daily limit was reached.

Recovery requires the confirmation phrase `RECOVER_PAPER_ENTRIES` and a fresh valuation that is back inside the daily and drawdown limits. The phrase is an explicit confirmation, not a secret. A consecutive-loss pause also requires `reset_loss_streak`. Recovery is refused while a limit is still breached. The high-water mark is not lowered.

## Correlation and emergencies

Correlation uses supplied tags: creator, narrative, liquidity provider, and driver. The first open position does not need tags. A later entry needs tags on itself and on every open position. Shared tags add those positions' marked value to one cluster. Missing tags do not become a correlation of zero; the entry is denied. Shield does not compute a statistical coefficient.

Emergency triggers, only from supplied evidence:

| Trigger | Evidence required |
|---|---|
| Liquidity removal | Both liquidity figures, and current/previous at or below the ratio |
| Price collapse | Both prices, and current/previous at or below the ratio |
| Whale selling | The flag and a source token |
| Smart-money exit | The flag and a source token |
| Abnormal impact | A supplied impact at or above the cap |
| Trading restriction | The flag and a source token |
| Market-data failure | A missing, future, or stale quote |

A one-sided liquidity pair does not become a liquidity-removal event. A whale flag without a source is ignored. Recording a trigger does not submit an order. A buy is blocked while that mint's emergency is active, or while a trading restriction or market-data failure has halted entries.

Exit kinds are `normal`, `signal`, `time`, `emergency`, and `take_profit`. A signal exit needs a signal reference. Shield does not invent the signal. A time exit uses the campaign open time and the configured holding time. An emergency exit needs fresh evidence or an active flag.

Re-entry after a flat campaign requires a `MATCHED` reconciliation of the closing order. Adding to an open campaign is denied.

## Persistence

Revision `0004_shield_risk_engine` stores the book, the UTC baselines, campaigns, stop plans, emergency flags, decisions, and local notices. Notices are rows in PostgreSQL. No external notifier is configured. The Risk Management page reads those rows. An empty database shows the documented defaults and states that no verified equity is stored.

## What this phase does not do

- It does not sign, submit, or simulate a Solana transaction.
- It does not call GMGN, an RPC, or a wallet.
- It does not turn a radar score into permission to trade.
- It does not add a pool-impact, latency, or historical cost model.
- It does not start Phase 6 backtesting or a paper broker that auto-fills stops.
