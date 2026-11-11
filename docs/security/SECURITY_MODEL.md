# Security model

Phase 3 scope. This document describes controls that exist in the repository today and names later controls as policy, not as implemented features.

## Data the process can see

| Data | Where it lives | Phase 1 behavior |
|---|---|---|
| Execution mode, host, port, log level | Environment or `.env` | Loaded by pydantic-settings. `.env` is gitignored. |
| Database URL | `CYVORA_DATABASE_URL` | Set on this PC. Password is never written to health output or the CYVORA log. |
| GMGN API key | `GMGN_API_KEY`, or `CYVORA_GMGN_API_KEY` | `SecretStr`. Logs, `repr`, and `model_dump` do not show the value. Health reports `configured` or `not_configured`. |
| Application status | Memory | Returned by `/health` and shown in the terminal. |
| Market data | GMGN read-only calls, then PostgreSQL | Stored as radar history and shown from that store. Not invented when the store is empty. |
| Wallet keys and orders | Not collected | `GMGN_PRIVATE_KEY` is ignored. Trade routes are refused before HTTP. |

## Credentials

The GMGN API key is read from `.env` and is not written to git. Telegram tokens, AI keys, wallet seeds, and private keys are not read. `.env.example` uses the literal placeholder `CHANGE_ME`. `.cursorignore` excludes `.env`, key files, and `secrets/`.

The Windows GMGN transport writes the key into a temporary curl config and deletes that directory before returning. Curl is started with `--disable` so a user curlrc cannot add a proxy. Redirects are not followed, so the key header is not sent to another host. A header value that contains a quote or a newline is refused before the file is used.

Agents must not print the environment and must not open `.env`.

## Execution authorization

`ExecutionMode` contains `READ_ONLY` and `PAPER` only. The settings validator rejects `LIVE`, `LIVE_LOCKED`, and `LIVE_AUTHORIZED` before the process starts. `assert_runtime_safe` repeats that check. `live_trading_enabled` in the health payload is the constant `false`.

There is no signer and no transaction builder. `GMGNExecutionGateway.submit` raises `GMGNExecutionBlocked` and does not open a socket. `GET /v1/user/wallet_holdings` raises before HTTP because the official client signs it.

## Local API

- Default bind is `127.0.0.1:8787`.
- `0.0.0.0` and other non-loopback hosts fail validation.
- CORS is not enabled.
- `/health` is unauthenticated because it exposes only process status.
- `/radar/latest`, `/radar/cycles`, and `/radar/watchlist` require `Authorization: Bearer` matching `CYVORA_API_TOKEN` (at least 16 characters). The comparison hashes both sides before `compare_digest`. A missing token is HTTP 503. A wrong token is HTTP 401 and the body does not echo the expected token.
- The desktop does not send that token. It reads PostgreSQL on the worker threads.
- Unexpected exceptions return `{"detail": "Internal server error"}`. The exception string is not logged.

## Database

Alembic will not connect when the URL is unset. Connection failures return a fixed sentence. The SQLAlchemy engine is created with `NullPool` for the check and is disposed immediately. Echo is left off so statements are not printed.

`0001_application_metadata` creates the metadata table. `0002_radar_intelligence` creates the radar history tables. Neither inserts a secret or grants remote access.

## Audit

Radar cycle saves and watchlist adds or removals insert `audit_events` with an action, a result, and a subject such as `sol:<address>`. The detail is a fixed sentence. It does not store the API key or the database URL. Trade intents and emergency stops are not recorded yet because those actions do not exist.

## Fail-safe defaults

- No execution.
- No automatic credential creation.
- No public listen address.
- No cloud deployment.
- No spending.
- A configured database that cannot be reached makes `/health` return HTTP 503. The desktop keeps running and shows `unreachable`.

## Known gaps

- `/health` has no authentication token. The mitigation is that it has no sensitive body and the socket is loopback. Radar routes do require the local token.
- Log files in `logs/` are local and gitignored. They can still contain messages a developer logs later. The logging rule is to keep secrets out of those messages.
- PostgreSQL, once installed, must be configured by the operator to listen on localhost and to use a password that is not reused from another service. The repository does not do that install.
