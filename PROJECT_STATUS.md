# Project status

Date: 2026-11-11.

## Current phase

Phase 8 — long-running local operations and cloud readiness. The definition of done below is met for the local design. Phase 9 has not started.

## Current milestone

A bounded supervisor can recover the stored paper book, record worker heartbeats, write a redacted diagnostic file, and dump a loopback database without printing the URL. The desktop probes loopback again after the API drops. No cloud resource was created, and no Windows service or scheduled task was registered.

## Completed work

- Phase 1 foundation, merged as PR #1.
- Phase 2 read-only GMGN client, merged as PR #2 (`4c48ad7`).
- Phase 3 radar cycle, merged as PR #3 (`e9ffb3c`).
- Phase 4 paper ledger, merged on `main` at `b4fcd8c`.
- Phase 5 Shield engine, merged on `main` at `b7cfd07`.
- Phase 6 simulation package, merged on `main` at `8de3e7e`.
- Phase 7 terminal pages, revision `0006_terminal`, authenticated `/terminal` routes, and the local stored-evidence analyst.
- Phase 8 supervisor, recovery, backup, diagnostics, local auth limits, desktop reconnect, and an undeployed cloud design. Revision `0007_operations`.

## In progress

Nothing inside Phase 8.

## Blockers

None for the local operations boundary. Live trading is still disabled. A paper approval, a profile, an analyst finding, and a completed recovery do not enable it. The GMGN key is still not bound to a wallet. Holdings, swaps, and wallet activity stay refused. There is no Solana RPC client. Telegram delivery is not configured. A persistent Windows task and any cloud host still need a separate authorization from the user.

## Tests

Recorded on 2026-11-11 after the Phase 8 run:

- `uv run ruff check .` passed.
- `uv run ruff format --check .` passed.
- `uv run mypy` passed.
- `uv run pytest` — 139 passed, 2 skipped. The skips are the opt-in GMGN and radar live smokes. One earlier full run reported a transient database `OperationalError` on the connectivity test; the database was reachable immediately afterward, and the repeated full run passed.
- `uv run python -m apps.desktop.main --smoke` printed `CYVORA_DESKTOP_SMOKE_OK` with database reachable, backend offline, and GMGN configured.
- Alembic upgrade applied `0007_operations`. `uv run alembic current` is `0007_operations (head)`.
- `uv run python -m operations.startup --ticks 1` printed `CYVORA_SUPERVISOR_OK` with radar skipped, freshness stale, portfolio and notices ok, entries not blocked, and wallet `not_authorized`.
- `uv run python -m operations.backup` wrote a local `pg_dump` file. The URL was not printed.
- `uv run python -m operations.diagnostics` wrote a redacted JSON file. The configured secrets were not in it.
- `scripts/register_supervisor_task.ps1` printed `CYVORA_SERVICE_NOT_INSTALLED`.

No API key or database URL is printed.

## Known limitations

- Cloudflare still blocks the Python TLS stack for `openapi.gmgn.ai` on this PC. Live GMGN calls use Windows `curl.exe`. The rate limiter is unchanged. The supervisor does not call GMGN unless `--include-radar` is set.
- Nautilus 1.231.0 on this wheel has fixed precision 9. A wider price stays in CYVORA `Decimal` and is not rounded into a Nautilus price.
- A `CurrencyPair` is a synthetic spot instrument. It is not a Solana swap. `OrderSubmitted` inside the Nautilus proof is not a signed transaction, and that proof is not the CYVORA backtest. The CYVORA backtest goes through Shield.
- GMGN candle volume is not base size. A single liquidity figure is not a reserve pair. Those bars do not fill. Reserves from a later radar snapshot are not copied onto an earlier candle.
- The constant-product impact for a buy equals the fraction of quote reserve spent. It is not a measured Solana AMM fee. The fee is the configured schedule.
- Displayed depth is one price level. A wide spread is refused when it exceeds the impact cap. It is not tightened to zero.
- A planned stop is not a guaranteed exit. The broker submits a paper sell through Shield and fills it at the pool or book.
- Sharpe and Sortino are per observation and are omitted below 30 return observations. They are not annualized. The terminal uses the same rule on stored equity changes.
- Walk-forward windows each start from the same paper equity. They are not one continuous portfolio. Selected parameters are not deployed.
- The simulation strategies are momentum, breakout, and stored-signal follow. They do not read a wallet.
- Backtests use an isolated ledger. They do not change the operator paper book. The modeled paper route does. That route stays blocked while recovery says the book is inconsistent or unreadable.
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
- `py -3.13` does not find the uv interpreter. Use `uv run`.

## Security

- Live mode names are rejected. A `paper_approved` decision does not enable them. The terminal has no control that can.
- `GMGN_PRIVATE_KEY` is not loaded. The paper path does not call `GMGNExecutionGateway` or a live Nautilus execution client.
- `/radar`, `/trading`, `/trading/simulation`, `/terminal`, and `/operations` require `CYVORA_API_TOKEN`. `/health` stays open and still returns status words only. Repeated authentication failures return HTTP 429. Auth rows do not store the token.
- `.env` is gitignored. The example file contains placeholders only. Container and task templates do not contain a database URL or a token.
- Simulation rows constrain `live_trading_enabled` to false. Run rows constrain `parameters_deployed` to false.
- Terminal profile, preference, and notification rows constrain live trading to false. Telegram delivery is constrained to false.
- Analyst findings set `authorizes_order` false. No external model is called.
- Recovery rows constrain wallet reconciliation to `not_authorized` and `wallet_assumed_flat` to false. Worker rows constrain `cloud_deployed` to false.

## Exact next actions

1. Do not start Phase 9 until the user asks.
2. Do not add a signing key, an RPC provider, a swap, or a Telegram bot token. Wallet binding is a separate decision.
3. Do not register the supervisor task or deploy the cloud design unless the user authorizes that specific step.
4. Phase 9, when requested, is a security and live-trading readiness review. It is not permission to trade live.

## Phase 8 checklist

| Done criterion | Result |
|---|---|
| Background worker lifecycle | One supervisor run records radar, freshness, paper-position, and notice ticks. Radar stays offline unless `--include-radar`. |
| Service supervision | Heartbeats, a restart limit, and failed-tick text that omits the exception. No Windows service was installed. |
| Startup management | The API stops leftover `RUNNING` strategies and writes a recovery report. `scripts/run_supervisor.ps1` defaults to one tick. |
| Recovery | Stored Shield presence, non-terminal paper orders, and position-versus-fill conflicts. Wallet not read and not assumed flat. New paper API entries block until the book is consistent. |
| Database backup | `pg_dump` for loopback only. Password stays off the command line. No scheduled backup was installed. |
| Health monitoring | `/health` adds worker, stored-cycle, queue, and websocket words. No new market-data call. |
| Local authentication | Existing bearer token, an in-process failure limit, and `auth_events` without the token. |
| Desktop reconnect | A 15-second loopback probe. The window does not start the API. |
| Exportable diagnostics | Redacted JSON under `diagnostics/`. The environment is not included. |
| Cloud design | `docs/operations/CLOUD_DESIGN.md` and `deploy/` templates. Nothing was deployed. |
| Paper only | Live flags stay false. The supervisor does not submit an order. |
| Phase 9 not started | No live-readiness report and no signer. |
