# Architecture

Phase 3 adds a read-only radar on top of the GMGN client. Strategies and execution are not in the repository. A score does not authorize an order.

## What runs today

```text
CYVORA Terminal (PySide6, Windows UI thread)
    |
    | StatusProbe thread          RadarLoadWorker / RadarCycleWorker
    v                             v
collect_status()                  PostgresRadarRepository
    |-- check_database()              |-- latest stored cycle
    \-- GET /health                   \-- one read-only GMGN cycle, then insert

CYVORA API (FastAPI, loopback only)
    |-- GET /health                         unauthenticated status words
    |-- GET /radar/latest                   bearer token, no GMGN call
    |-- POST /radar/cycles                  bearer token, one read-only cycle
    \-- POST/DELETE /radar/watchlist        bearer token, PostgreSQL only
```

The desktop and the API are separate processes. The desktop does not start the API. Both read the same settings object. There is no message bus. GMGN is a library the process calls directly. Health does not call it. The execution gateway has no HTTP client. Radar pages show the latest stored cycle or an explicit empty state.

## Modules

| Module | Role |
|---|---|
| `config.settings` | Loads `CYVORA_*` settings and rejects live modes, public hosts, and non-PostgreSQL URLs. |
| `monitoring.logging` | Writes the `cyvora` logger to stderr and `logs/cyvora.log`. |
| `monitoring.health` | Builds a `StatusSnapshot` with application, database, backend, and GMGN configuration state. |
| `database.connection` | Opens a short-lived SQLAlchemy engine when a URL is configured. |
| `database.models` | `application_metadata` and the radar history tables. |
| `database.migrations` | Alembic revisions `0001_application_metadata` and `0002_radar_intelligence`. |
| `database.repositories` | `PostgresRadarRepository`, the radar store used by the API and the terminal. |
| `apps.api` | Factory `create_app`. `/health` plus authenticated `/radar` routes. |
| `apps.desktop` | Terminal window, theme, navigation, and stored radar pages. |
| `domain` | `ExecutionMode`, radar categories, errors, and status dataclasses. |
| `integrations.gmgn` | Allowlisted GMGN reads, rate limiting, and a gateway that refuses trades. |
| `intelligence` | One radar cycle, indicators, security, liquidity, smart money, whales, and the score. |

## Data that is stored

`application_metadata` remains the Phase 1 table (`id`, `app_name`, `schema_revision`, timezone-aware `created_at`). It is not seeded.

Revision `0002_radar_intelligence` adds history that a later cycle inserts and does not overwrite:

- `tokens`, `radar_cycles`, `token_observations`
- `token_analyses`, `token_candles`, `indicator_signals`
- `security_assessments`, `liquidity_snapshots`
- `smart_money_events`, `whale_events`
- `watchlist_items` (removal sets `active` false)
- `audit_events` for the cycle and watchlist actions

Amounts are `Numeric(38, 18)`. The breakdown JSON stores the public score fields the terminal reads back. Orders are not stored.

## Planned boundaries

These names are reserved for later phases. They are not stubbed in code.

1. CYVORA Terminal remains the Windows control surface.
2. CYVORA API remains a loopback service. `/radar` requires the local bearer token. `/health` stays unauthenticated.
3. CYVORA Core will own strategy lifecycle and simulated execution. NautilusTrader, if adopted, stays behind that boundary. Solana swaps will not be forced into exchange order types.
4. `integrations.gmgn` is the market-data boundary. Radar calls that client. It does not add routes. There is no strategy.
5. PostgreSQL remains the system of record.

## Execution lifecycle

There is no order lifecycle. The only mode flag is `READ_ONLY` or `PAPER`, and both mean "do not submit a transaction". `GMGNExecutionGateway.submit` discards the payload and raises. A future live path has to pass settings validation that currently rejects it.

## Security boundary

Secrets stay in an untracked `.env` file. The health route returns status words, not configuration values. See `docs/security/SECURITY_MODEL.md`.
