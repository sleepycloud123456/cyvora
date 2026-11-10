# Architecture

Phase 2 adds a read-only GMGN client beside the Phase 1 foundation. Radar, strategies, and execution are still not in the repository.

## What runs today

```text
CYVORA Terminal (PySide6, Windows UI thread)
    |
    | StatusProbe thread
    v
collect_status()
    |-- check_database() ---- optional local PostgreSQL
    \-- probe_backend_http() -- GET http://127.0.0.1:8787/health

CYVORA API (FastAPI, loopback only)
    \-- GET /health -- collect_status(probe_backend=False)
```

The desktop and the API are separate processes. The desktop does not start the API. Both read the same settings object. There is no message bus. GMGN is a library the process calls directly. Health does not call it. The execution gateway has no HTTP client.

## Modules

| Module | Role |
|---|---|
| `config.settings` | Loads `CYVORA_*` settings and rejects live modes, public hosts, and non-PostgreSQL URLs. |
| `monitoring.logging` | Writes the `cyvora` logger to stderr and `logs/cyvora.log`. |
| `monitoring.health` | Builds a `StatusSnapshot` with application, database, backend, and GMGN configuration state. |
| `database.connection` | Opens a short-lived SQLAlchemy engine when a URL is configured. |
| `database.models` | `application_metadata` table. |
| `database.migrations` | Alembic revision `0001_application_metadata`. |
| `apps.api` | Factory `create_app`. One route, `/health`. |
| `apps.desktop` | Terminal window, theme, and navigation. |
| `domain` | `ExecutionMode`, errors, and status dataclasses. |
| `integrations.gmgn` | Allowlisted GMGN reads, rate limiting, and a gateway that refuses trades. |

## Data that is stored

The only designed table is `application_metadata`:

- `id`
- `app_name`
- `schema_revision`
- `created_at` as a timezone-aware timestamp

Revision `0001_application_metadata` is applied on this machine. The table is not seeded. GMGN responses are not stored. Orders and audit rows are not implemented.

## Planned boundaries

These names are reserved for later phases. They are not stubbed in code.

1. CYVORA Terminal remains the Windows control surface.
2. CYVORA API remains a loopback service and must authenticate any route beyond health before that route is added.
3. CYVORA Core will own strategy lifecycle and simulated execution. NautilusTrader, if adopted, stays behind that boundary. Solana swaps will not be forced into exchange order types.
4. `integrations.gmgn` is the market-data boundary. Strategies must not call HTTP themselves. Phase 2 has no strategy.
5. PostgreSQL remains the system of record.

## Execution lifecycle

There is no order lifecycle. The only mode flag is `READ_ONLY` or `PAPER`, and both mean "do not submit a transaction". `GMGNExecutionGateway.submit` discards the payload and raises. A future live path has to pass settings validation that currently rejects it.

## Security boundary

Secrets stay in an untracked `.env` file. The health route returns status words, not configuration values. See `docs/security/SECURITY_MODEL.md`.
