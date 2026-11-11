# Security model

Phase 9 scope. This document describes controls that exist in the repository today. The readiness report names chain controls that are still absent. It does not implement them.

## Data the process can see

| Data | Where it lives | Phase 1 behavior |
|---|---|---|
| Execution mode, host, port, log level | Environment or `.env` | Loaded by pydantic-settings. `.env` is gitignored. |
| Database URL | `CYVORA_DATABASE_URL` | Set on this PC. Password is never written to health output or the CYVORA log. |
| GMGN API key | `GMGN_API_KEY`, or `CYVORA_GMGN_API_KEY` | `SecretStr`. Logs, `repr`, and `model_dump` do not show the value. Health reports `configured` or `not_configured`. |
| Application status | Memory | Returned by `/health` and shown in the terminal. |
| Market data | GMGN read-only calls, then PostgreSQL | Stored as radar history and shown from that store. Not invented when the store is empty. |
| Paper orders and positions | PostgreSQL | Explicit simulated rows. Shield stores `paper_approved` or `denied`. |
| Simulation reports | PostgreSQL | Datasets, runs, and fill assumptions. Parameters are not deployed. |
| Terminal profiles and notices | PostgreSQL | Paper labels and local notices. Live trading and Telegram delivery are constrained false. |
| Wallet keys | Not collected | `GMGN_PRIVATE_KEY` is ignored. Trade routes are refused before HTTP. |

## Credentials

The GMGN API key is read from `.env` and is not written to git. Telegram tokens, AI keys, wallet seeds, and private keys are not read. The terminal rejects a request that tries to enable Telegram delivery or live trading. `.env.example` uses the literal placeholder `CHANGE_ME`. `.cursorignore` excludes `.env`, key files, and `secrets/`.

The Windows GMGN transport writes the key into a temporary curl config and deletes that directory before returning. Curl is started with `--disable` so a user curlrc cannot add a proxy. Redirects are not followed, so the key header is not sent to another host. A header value that contains a quote or a newline is refused before the file is used.

Agents must not print the environment and must not open `.env`.

## Execution authorization

`ExecutionMode` contains `READ_ONLY` and `PAPER` only. The settings validator rejects `LIVE`, `LIVE_LOCKED`, and `LIVE_AUTHORIZED` before the process starts. `assert_runtime_safe` repeats that check. `live_trading_enabled` in the health payload is the constant `false`. `readiness.live_gate` returns `authorized=False` and cannot be given a grant flag. Readiness rows constrain `authorization_state` to `not_authorized`.

There is no signer and no transaction builder. `GMGNExecutionGateway.submit` raises `GMGNExecutionBlocked` and does not open a socket. `refuse_live_execution` raises before a store write. `GET /v1/user/wallet_holdings` raises before HTTP because the official client signs it.

`PAPER` may store a simulated order after Shield evaluates it. The gateway rejects a request that sets `shield_approved`. Read-only mode stores no order. The order table's check constraints reject a live state and a non-paper mode. Shield decisions are `paper_approved`, `denied`, or the legacy value `not_authorized`. Decision rows constrain `live_trading_enabled` to false. Simulation runs constrain `parameters_deployed` to false and `live_trading_enabled` to false. The Nautilus proof uses `BacktestEngine` only. It does not register a live execution client, and the Phase 6 backtest does not call it.

## Local API

- Default bind is `127.0.0.1:8787`.
- `0.0.0.0` and other non-loopback hosts fail validation.
- CORS is not enabled.
- `/health` is unauthenticated because it exposes only process status. Worker, cycle, queue, websocket, and kill-switch words are included. There is still no websocket server. `/docs`, `/redoc`, and `/openapi.json` are disabled.
- `/radar`, `/trading`, `/terminal`, and `/operations` require `Authorization: Bearer` matching `CYVORA_API_TOKEN` (at least 16 characters). The comparison hashes both sides before `compare_digest`. A missing token is HTTP 503. A wrong token is HTTP 401 and the body does not echo the expected token. Repeated failures in the process return HTTP 429. `auth_events` stores the result word, not the token.
- The desktop does not send that token. It reads PostgreSQL on the worker threads and probes loopback health every 15 seconds. It does not start the API.
- Unexpected exceptions return `{"detail": "Internal server error"}`. The exception string is not logged.

## Database

Alembic will not connect when the URL is unset. Connection failures return a fixed sentence. The SQLAlchemy engine is created with `NullPool` for the check and is disposed immediately. Echo is left off so statements are not printed.

`0001_application_metadata` creates the metadata table. `0002_radar_intelligence` creates the radar history tables. `0003_trading_infrastructure` creates the paper ledger. `0004_shield_risk_engine` creates the paper risk book. `0005_simulation` creates the simulation tables. `0006_terminal` creates profiles and local notices. `0007_operations` creates worker, recovery, backup, and authentication rows. None of them inserts a secret or grants remote access. Recovery rows cannot record a wallet read or a flat wallet.

## Audit

Radar cycle saves and watchlist adds or removals insert `audit_events` with an action, a result, and a subject such as `sol:<address>`. Paper orders insert `trading_order_events` with the state and a fixed note. The note records `TradeIntentCreated` and `ExecutionConfirmed` as simulator events. Shield inserts decision and notice rows for paper approvals, denials, breaches, emergencies, and recoveries. Those rows do not store the API key, the database URL, or a signature. An emergency notice does not submit an order.

## Fail-safe defaults

- No chain execution. Paper mode can store a simulated order only.
- No automatic credential creation.
- No public listen address.
- No cloud deployment. The design files under `deploy/` were not applied. Backup dumps and diagnostic files stay in gitignored directories.
- No spending.
- A configured database that cannot be reached makes `/health` return HTTP 503. The desktop keeps running and shows `unreachable`.

## Kill switch

`readiness_controls` stores one latch. Engaging it refuses new operator paper orders. It does not submit a sell, sign, or change Shield limits. Releasing it requires the confirmation word `RELEASE` from the desktop dialog or from an authenticated request. The word is not stored. Resume of paper entries does not clear the latch. If the row cannot be read, new operator paper orders stay blocked. An isolated backtest does not consult the latch.

The database URL is omitted from `repr(Settings)` and from `model_dump`. `get_settings` does not re-raise the pydantic error object, because that object can contain the URL. `pg_dump` is accepted only from a Program Files PostgreSQL directory. The GMGN curl transport escapes backslashes and refuses a request whose host is not `openapi.gmgn.ai`.

## Known gaps

- `/health` has no authentication token. The mitigation is that it has no sensitive body and the socket is loopback. Radar, trading, terminal, and operations routes require the local token.
- The authentication failure count lives in the process. A restart clears it.
- The GitHub repository is public. `.env` is not in history. Making the repository private is an operator decision.
- `fsspec` 2026.2.0 is pinned by NautilusTrader 1.231.0 and has PYSEC-2026-4217. CYVORA does not call the affected API. See `docs/security/SECURITY_REVIEW.md`.
- Log files in `logs/` are local and gitignored. They can still contain messages a developer logs later. The logging rule is to keep secrets out of those messages.
- PostgreSQL, once installed, must be configured by the operator to listen on localhost and to use a password that is not reused from another service. The repository does not do that install.
