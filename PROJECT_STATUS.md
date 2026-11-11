# Project status

Date: 2026-11-11.

## Current phase

Phase 9 — security review and live-trading readiness. The definition of done below is met. Live trading is not authorized.

## Current milestone

The live-trading gate stays closed. A checklist marked fully present still returns `authorized: false`. The operator kill switch can block new operator paper orders and was verified engaged, then released, on the local database. No wallet was bound and no transaction was signed.

## Completed work

- Phase 1 foundation, merged as PR #1.
- Phase 2 read-only GMGN client, merged as PR #2 (`4c48ad7`).
- Phase 3 radar cycle, merged as PR #3 (`e9ffb3c`).
- Phase 4 paper ledger, merged on `main` at `b4fcd8c`.
- Phase 5 Shield engine, merged on `main` at `b7cfd07`.
- Phase 6 simulation package, merged on `main` at `8de3e7e`.
- Phase 7 terminal pages, revision `0006_terminal`, authenticated `/terminal` routes, and the local stored-evidence analyst.
- Phase 8 supervisor, recovery, backup, diagnostics, local auth limits, desktop reconnect, and an undeployed cloud design. Revision `0007_operations`.
- Phase 9 security review, closed live-trading gate, kill switch, and runbooks. Revision `0008_readiness`.

## In progress

Nothing inside Phase 9.

## Blockers

None for the readiness boundary. Live trading is still disabled. The report, a paper approval, a profile, an analyst finding, and a released kill switch do not enable it. The GMGN key is still not bound to a wallet. Holdings, swaps, and wallet activity stay refused. There is no Solana RPC client. Telegram delivery is not configured. A persistent Windows task and any cloud host still need a separate authorization from the user.

## Tests

Recorded on 2026-11-11 after the Phase 9 run:

- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.
- `uv run mypy` passed.
- `uv run pytest` — 149 passed, 2 skipped. The skips are the opt-in GMGN and radar live smokes.
- `uv run python -m apps.desktop.main --smoke` printed `CYVORA_DESKTOP_SMOKE_OK` with database reachable, backend offline, and GMGN configured.
- Alembic upgrade applied `0008_readiness`. `uv run alembic current` is `0008_readiness (head)`.
- The local kill-switch row was engaged and then released. A wrong confirmation was refused. The stored latch was left released. `live_trading_enabled` stayed false and `authorization_state` stayed `not_authorized`.
- `uv run python -m readiness` printed `ready_for_live: false`, `kill_switch: released`, and `live_trading_enabled=false`.
- `uv run --with pip-audit pip-audit` reported `fsspec` 2026.2.0 (PYSEC-2026-4217), pinned by NautilusTrader 1.231.0. CYVORA does not call the affected API. The Nautilus pin was not changed.

No API key or database URL is printed.

## Known limitations

- Cloudflare still blocks the Python TLS stack for `openapi.gmgn.ai` on this PC. Live GMGN calls use Windows `curl.exe`. The rate limiter is unchanged. The supervisor does not call GMGN unless `--include-radar` is set.
- `fsspec==2026.2.0` is required by NautilusTrader 1.231.0. The reference-filesystem advisory is not patched inside that pin. CYVORA does not open a reference filesystem.
- The GitHub repository is public. `.env` is not in its history. Changing visibility is an operator decision.
- Nautilus 1.231.0 on this wheel has fixed precision 9. A wider price stays in CYVORA `Decimal` and is not rounded into a Nautilus price.
- A `CurrencyPair` is a synthetic spot instrument. It is not a Solana swap. `OrderSubmitted` inside the Nautilus proof is not a signed transaction, and that proof is not the CYVORA backtest. The CYVORA backtest goes through Shield.
- GMGN candle volume is not base size. A single liquidity figure is not a reserve pair. Those bars do not fill. Reserves from a later radar snapshot are not copied onto an earlier candle.
- The constant-product impact for a buy equals the fraction of quote reserve spent. It is not a measured Solana AMM fee. The fee is the configured schedule.
- Displayed depth is one price level. A wide spread is refused when it exceeds the impact cap. It is not tightened to zero.
- A planned stop is not a guaranteed exit. The broker submits a paper sell through Shield and fills it at the pool or book.
- Sharpe and Sortino are per observation and are omitted below 30 return observations. They are not annualized. The terminal uses the same rule on stored equity changes.
- Walk-forward windows each start from the same paper equity. They are not one continuous portfolio. Selected parameters are not deployed.
- The simulation strategies are momentum, breakout, and stored-signal follow. They do not read a wallet.
- Backtests use an isolated ledger. They do not change the operator paper book and they do not consult the kill switch. The modeled paper route does. That route stays blocked while recovery says the book is inconsistent or unreadable, and while the kill switch is engaged or unreadable.
- No Solana RPC, account inspection, or chain confirmation client is included. Recovery does not assume the wallet is flat.
- `2.0.0` final was not on PyPI on 2026-11-11. The `2.0.0rc*` builds are not installed.
- Wallet SOL and USD value are not available. Verified equity is the last Shield baseline.
- A missing open-position mark is not treated as zero. Mixed quotes are not summed.
- The latest radar cycle does not store a market-condition label.
- Smart-money accumulation and application-stopped notices have no stored source, so they are not emitted.
- Entry and exit markers are not drawn on candles. Buy and sell pressure is not a stored series. Liquidity history is stored and is not a separate chart.
- A profile signal threshold is recorded and is not applied to the score or to Shield.
- Telegram delivery is off. No bot token is loaded.
- There is no websocket server and no external queue. Health says so.
- Retention is a plan. Audit events and backtests are not deleted.
- The cloud Dockerfile and compose file were not built or started. The scheduled-task script was not run with `-ConfirmInstall`.
- `pg_dump` is accepted only from a Program Files PostgreSQL install. A copy earlier on `PATH` is ignored.
- `py -3.13` does not find the uv interpreter. Use `uv run`.

## Security

- Live mode names are rejected. A `paper_approved` decision does not enable them. The readiness report cannot enable them. The terminal has no control that can.
- `GMGN_PRIVATE_KEY` is not loaded. The paper path does not call `GMGNExecutionGateway` or a live Nautilus execution client.
- `/radar`, `/trading`, `/trading/simulation`, `/terminal`, and `/operations` require `CYVORA_API_TOKEN`. `/health` stays open and still returns status words only. `/docs` and `/openapi.json` are disabled. Repeated authentication failures return HTTP 429. A bearer value longer than 4096 characters is rejected before it is hashed. Auth rows do not store the token.
- The kill switch is a database row. Resume and the analyst cannot release it. It was left released after the verification above.
- `.env` is gitignored and has no commit. The example file contains placeholders only. Container and task templates do not contain a database URL or a token.
- `repr(Settings)` and `model_dump` do not include the database password. `get_settings` does not re-raise the pydantic input value.
- Simulation rows constrain `live_trading_enabled` to false. Run rows constrain `parameters_deployed` to false.
- Terminal profile, preference, and notification rows constrain live trading to false. Telegram delivery is constrained to false.
- Readiness rows constrain live trading to false and authorization to `not_authorized`.
- Analyst findings set `authorizes_order` false. No external model is called.
- Recovery rows constrain wallet reconciliation to `not_authorized` and `wallet_assumed_flat` to false. Worker rows constrain `cloud_deployed` to false.

## Exact next actions

1. Do not enable live trading. The decisions required before that can be discussed are listed in `docs/security/LIVE_READINESS.md`.
2. Do not add a signing key, an RPC provider, a swap, or a Telegram bot token. Wallet binding is a separate decision.
3. Do not register the supervisor task or deploy the cloud design unless the user authorizes that specific step.
4. Decide whether the public GitHub repository should stay public before any live operational notes are added.

## Phase 9 checklist

| Done criterion | Result |
|---|---|
| Wallet compatibility | Recorded absent. No wallet client was added. |
| Execution permissions | Live mode names stay rejected. The gate has no granted state. |
| Risk enforcement | Shield still decides paper orders. A paper approval is not a live order. |
| Transaction simulation | Paper simulator only. No chain simulation was added. |
| Transaction confirmation | A paper `CONFIRMED` state stays a simulator word. |
| Reconciliation | Paper book only. Wallet reconciliation stays `not_authorized`. |
| Duplicate prevention | A repeated paper idempotency key returns the stored order while the kill switch is engaged. |
| Emergency controls | Kill switch engages, blocks a new operator paper order, and releases only with the confirmation word. |
| Failure recovery | Existing paper recovery remains. An unreadable kill-switch row blocks new operator paper orders. |
| API disconnection | GMGN transport behavior is unchanged. No live order is left in flight. |
| Balance verification | Recorded absent. No balance was read. |
| Spending limits | Paper Shield limits remain. No chain spending limit was added. |
| Audit trails | Readiness events store the action and not the confirmation word. |
| Security review | `docs/security/SECURITY_REVIEW.md`. Fixed findings are in the code. Open findings are listed there. |
| Live trading | Disabled. `ready_for_live` is false. |
