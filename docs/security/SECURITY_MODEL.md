# Security model

Phase 1 scope. This document describes controls that exist in the repository today and names later controls as policy, not as implemented features.

## Data the process can see

| Data | Where it lives | Phase 1 behavior |
|---|---|---|
| Execution mode, host, port, log level | Environment or `.env` | Loaded by pydantic-settings. `.env` is gitignored. |
| Database URL | `CYVORA_DATABASE_URL` | Optional. Password is never written to health output or the CYVORA log. |
| Application status | Memory | Returned by `/health` and shown in the terminal. |
| Market, wallet, and order data | Not collected | No client exists. |

## Credentials

No GMGN key, Telegram token, AI key, wallet seed, or private key is read or stored. `.env.example` uses the literal placeholder `CHANGE_ME` inside a comment. `.cursorignore` excludes `.env`, key files, and `secrets/`.

Agents must not print the environment and must not open `.env`.

## Execution authorization

`ExecutionMode` contains `READ_ONLY` and `PAPER` only. The settings validator rejects `LIVE`, `LIVE_LOCKED`, and `LIVE_AUTHORIZED` before the process starts. `assert_runtime_safe` repeats that check. `live_trading_enabled` in the health payload is the constant `false`.

There is no signer, no swap function, and no transaction builder.

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
