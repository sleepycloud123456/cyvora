# Live-trading readiness

Date: 2026-11-11. Phase 9 is preparation. `ready_for_live` is false. `live_trading_enabled` is false. `authorization_state` is `not_authorized`. No function in this repository can set those to a granted state.

`GET /operations/readiness` returns the same report the desktop health card summarizes. It requires the local bearer token. The report lists controls. It does not open the gate.

## Gate

`readiness.live_gate` builds a `GateDecision` with `authorized=False`. The function does not take an authorization flag. A test passes a checklist where every item is `present` and the decision stays closed. Settings still reject `LIVE`, `LIVE_LOCKED`, and `LIVE_AUTHORIZED`. Database checks on the new readiness rows reject any other authorization state and reject `live_trading_enabled = true`.

A later phase that wants to open the gate has to be a separate change, after the operator decisions below, and it still cannot treat a paper approval as a live order.

## Checklist

| Control | Status | What the code does today |
|---|---|---|
| Wallet compatibility | Absent | No wallet is bound. `GMGN_PRIVATE_KEY` is not loaded. Holdings and wallet activity are refused before HTTP. |
| Execution permissions | Present as a lock | Only `READ_ONLY` and `PAPER`. The live gateway raises and does not open a socket. |
| Risk enforcement | Partial | Shield approves or denies every new paper order on the operator book. A paper approval cannot submit a live order. Chain spending is not checked. |
| Transaction simulation | Partial | The paper simulator prices a local order. There is no Solana simulation and no RPC. |
| Transaction confirmation | Partial | `CONFIRMED` on a paper order is a simulator word. It is not a chain confirmation. |
| Reconciliation | Partial | Stored paper orders and positions are compared. Wallet reconciliation stays `not_authorized`. A missing wallet is not treated as flat. |
| Duplicate prevention | Partial | A repeated paper idempotency key returns the stored order, including while the kill switch is engaged. That is not chain deduplication. |
| Emergency controls | Present | The kill switch blocks new operator paper orders. It does not flatten, sign, or submit. |
| Failure recovery | Partial | Startup recovery reads the paper book and blocks new paper API entries when the book is inconsistent or unreadable. |
| API disconnection | Partial | GMGN transport errors are recorded. Retries stay bounded. No live order can be in flight. |
| Balance verification | Absent | Wallet SOL and token balances are not read. |
| Spending limits | Partial | Shield applies paper allocation, loss, and liquidity limits. There is no on-chain spend limit. |
| Audit trails | Present | Paper order events, Shield decisions, auth results, and kill-switch changes are stored. Secrets are not columns. |

## Kill switch

The latch is one row in `readiness_controls`. Migration `0008_readiness` inserts it released. `readiness_events` records engage, release, a refused confirmation, and a refused new order. The confirmation text is not stored.

Engage and release:

- Desktop Settings, after a confirmation dialog. The worker sends the word `ENGAGE` or `RELEASE` only after that dialog. Resume paper entries does not release the switch.
- `POST /operations/kill-switch/engage` and `POST /operations/kill-switch/release` with `{"confirm": "ENGAGE"}` or `{"confirm": "RELEASE"}`. The routes require the bearer token. A wrong word is HTTP 422 and does not echo the submitted text.

While the latch is engaged, or the row cannot be read, `PaperExecutionGateway` raises before a new operator order is stored. A repeated idempotency key still returns the order that was already stored. The modeled paper route uses that gateway. An isolated backtest does not. The supervisor does not submit orders.

The switch does not cancel anything on a chain. There is nothing on a chain to cancel.

## Operator decisions required before live trading can be discussed

None of these have been provided. Supplying them in a later message is what "explicit authorization" has to cover. This phase does not implement them.

1. A separate explicit authorization to enable live trading, after reading this report and `docs/security/SECURITY_REVIEW.md`.
2. A wallet decision: which path may sign, if any. Do not send a seed phrase, a private key, or a wallet password. Saying "use the GMGN embedded wallet" or "do not load `GMGN_PRIVATE_KEY`" is the decision. The key itself stays out of chat and out of git.
3. An RPC decision: which provider, which reads are allowed, and the monthly cost inside the existing budget. No provider is integrated.
4. Real spending limits: maximum loss per day, per trade, and a SOL reserve for fees, as numbers the operator accepts. Shield's paper defaults are not those numbers.
5. Kill-switch scope: whether a future live switch must also cancel an in-flight transaction, and who is allowed to release it. Today any desktop operator on this PC, or any holder of the local API token, can release it with the confirmation word.
6. Whether `https://github.com/sleepycloud123456/cyvora` should remain public before any live operational notes are added.
7. Acceptance that paper fills, radar scores, and analyst findings do not predict a live fill and cannot authorize one.
8. Separate authorization for a paid GMGN plan, a Telegram bot, a Windows service, or a cloud host. None of those is turned on here.
9. Confirmation that the API stays on loopback, or a separate security design before any other bind.

## Dependency review

`uv run --with pip-audit pip-audit` on 2026-11-11 reported one finding: `fsspec` 2026.2.0, PYSEC-2026-4217, fixed in 2026.6.0. The issue is template rendering inside `ReferenceFileSystem` when that API is given an attacker-controlled references document. NautilusTrader 1.231.0 requires `fsspec==2026.2.0`. CYVORA does not call that API. The lock was not changed, and Nautilus was not replaced. The GMGN Windows transport remains `curl.exe` with the existing rate limiter. No package was added to `pyproject.toml`.
