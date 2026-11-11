# Architecture

Phase 5 adds Shield beside the paper ledger. A score does not authorize an order. A Shield paper approval is not a chain transaction.

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
    |-- POST/DELETE /radar/watchlist        bearer token, PostgreSQL only
    |-- GET /trading/status                 bearer token, no venue call
    |-- GET /trading/orders, positions, strategies
    |-- POST /trading/strategies            register, start, or stop a slot
    |-- POST /trading/paper/orders          paper mode only, Shield then the simulator
    |-- GET/PUT /trading/shield             stored paper risk book and limits
    \-- POST /trading/live/{operation}      always refused
```

The desktop and the API are separate processes. The desktop does not start the API. Both read the same settings object. There is no message bus. GMGN is a library the radar calls directly. Health does not call it. The GMGN execution gateway has no HTTP client. The paper gateway does not call GMGN. Radar pages show the latest stored cycle or an empty state. Open Positions, Trade History, and Strategies show stored simulation rows or an empty state.

## Modules

| Module | Role |
|---|---|
| `config.settings` | Loads `CYVORA_*` settings and rejects live modes, public hosts, and non-PostgreSQL URLs. |
| `monitoring.logging` | Writes the `cyvora` logger to stderr and `logs/cyvora.log`. |
| `monitoring.health` | Builds a `StatusSnapshot` with application, database, backend, and GMGN configuration state. |
| `database.connection` | Opens a short-lived SQLAlchemy engine when a URL is configured. |
| `database.models` | Application metadata, radar history, and the paper ledger. |
| `database.migrations` | Alembic revisions through `0004_shield_risk_engine`. |
| `database.repositories` | Radar history and the paper ledger. |
| `apps.api` | Factory `create_app`. `/health`, authenticated `/radar`, and authenticated `/trading`. |
| `apps.desktop` | Terminal window, theme, navigation, stored radar pages, and the simulation ledger. |
| `domain` | `ExecutionMode`, radar categories, paper records, errors, and status dataclasses. |
| `integrations.gmgn` | Allowlisted GMGN reads, rate limiting, and a gateway that refuses trades. |
| `integrations.solana` | Adapts supplied observations and GMGN candles into market contracts. No RPC. |
| `intelligence` | One radar cycle, indicators, security, liquidity, smart money, whales, and the score. |
| `trading` | Paper gateway, order states, positions, strategy registry, and the Nautilus proof. |
| `shield` | Deterministic paper risk decisions. Approval cannot enable a live order. |

## Data that is stored

`application_metadata` remains the Phase 1 table (`id`, `app_name`, `schema_revision`, timezone-aware `created_at`). It is not seeded.

Revision `0002_radar_intelligence` adds history that a later cycle inserts and does not overwrite:

- `tokens`, `radar_cycles`, `token_observations`
- `token_analyses`, `token_candles`, `indicator_signals`
- `security_assessments`, `liquidity_snapshots`
- `smart_money_events`, `whale_events`
- `watchlist_items` (removal sets `active` false)
- `audit_events` for the cycle and watchlist actions

Amounts are `Numeric(38, 18)`. The breakdown JSON stores the public score fields the terminal reads back.

Revision `0003_trading_infrastructure` adds the paper ledger:

- `trading_instruments`, `trading_strategies`, `trading_orders`
- `trading_order_events`, `trading_positions`, `trading_reconciliations`

Check constraints keep `simulated` true and `execution_mode` at `PAPER`. `shield_decision` is `not_authorized` for legacy rows, or `paper_approved` or `denied` for Shield. They reject `SUBMISSION_PENDING`, `SUBMITTED`, and `CONFIRMATION_PENDING`.

Revision `0004_shield_risk_engine` adds the Shield book: controls, UTC-day baselines, campaigns, stop plans, emergency flags, decisions, and local notices. Decision rows constrain `live_trading_enabled` to false.

## Boundaries

1. CYVORA Terminal remains the Windows control surface.
2. CYVORA API remains a loopback service. `/radar` and `/trading` require the local bearer token. `/health` stays unauthenticated.
3. CYVORA Core owns the strategy registry and simulated execution. NautilusTrader 1.231.0 stays behind `trading/nautilus`. Solana swaps are not represented as exchange order types.
4. `integrations.gmgn` is the market-data boundary. Radar calls that client. It does not add routes. Radar does not register a strategy.
5. PostgreSQL remains the system of record.

Signal strategies, the Phase 6 paper broker, and cloud deployment are not in the repository.

## Execution lifecycle

`READ_ONLY` does not store a simulated order. `PAPER` may store one. Both modes mean "do not submit a transaction". `GMGNExecutionGateway.submit` discards the payload and raises. `refuse_live_execution` raises before a store write or a socket. A future live path has to pass settings validation that currently rejects it.

A paper order is created, validated, marked simulation-pending, marked simulation-passed, and then confirmed or failed. Confirmation is the local simulator's result. Reconciliation can move that row to `UNKNOWN` when a report is missing or disagrees. It does not change the position and it does not send another order.

The API sets every `RUNNING` strategy to `STOPPED` when the process starts. Starting a strategy and submitting an intent both require `PAPER`. Shield then stores `paper_approved` or `denied`. A paper approval does not change the live-execution refusal.

## Security boundary

Secrets stay in an untracked `.env` file. The health route returns status words, not configuration values. See `docs/security/SECURITY_MODEL.md`.
