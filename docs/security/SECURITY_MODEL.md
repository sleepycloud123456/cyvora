# Security model

Phase 2 scope. This document describes controls that exist in the repository today and names later controls as policy, not as implemented features.

## Data the process can see

| Data | Where it lives | Phase 1 behavior |
|---|---|---|
| Execution mode, host, port, log level | Environment or `.env` | Loaded by pydantic-settings. `.env` is gitignored. |
| Database URL | `CYVORA_DATABASE_URL` | Set on this PC. Password is never written to health output or the CYVORA log. |
| GMGN API key | `GMGN_API_KEY`, or `CYVORA_GMGN_API_KEY` | `SecretStr`. Logs, `repr`, and `model_dump` do not show the value. Health reports `configured` or `not_configured`. |
| Application status | Memory | Returned by `/health` and shown in the terminal. |
| Market data | GMGN read-only calls | Not stored. Not shown in the terminal. |
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
- `/health` is unauthenticated because it exposes only process status. Any future route that reads configuration, portfolio state, or control actions must require authentication before it is merged.
- Unexpected exceptions return `{"detail": "Internal server error"}`. The exception string is not logged.

## Database

Alembic will not connect when the URL is unset. Connection failures return a fixed sentence. The SQLAlchemy engine is created with `NullPool` for the check and is disposed immediately. Echo is left off so statements are not printed.

The migration creates `application_metadata` only. It does not insert a secret and does not grant remote access.

## Audit

Configuration changes, trade intents, and emergency stops are not recorded yet because those actions do not exist. When they do, the audit row must store the action and the result, not a credential.

## Fail-safe defaults

- No execution.
- No automatic credential creation.
- No public listen address.
- No cloud deployment.
- No spending.
- A configured database that cannot be reached makes `/health` return HTTP 503. The desktop keeps running and shows `unreachable`.

## Known gaps

- `/health` has no authentication token. The mitigation is that it has no sensitive body and the socket is loopback.
- Log files in `logs/` are local and gitignored. They can still contain messages a developer logs later. The logging rule is to keep secrets out of those messages.
- PostgreSQL, once installed, must be configured by the operator to listen on localhost and to use a password that is not reused from another service. The repository does not do that install.
