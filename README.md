# CYVORA

CYVORA is a local-first Windows platform for Solana memecoin research, simulation, and, only after a later explicit authorization, supervised trading. This repository has the Phase 1 foundation, a Phase 2 read-only GMGN client, a Phase 3 radar, a Phase 4 paper ledger, a Phase 5 Shield risk engine, a Phase 6 simulation backtest, the Phase 7 terminal pages, a Phase 8 local supervisor, and a Phase 9 security review with live trading still locked. The desktop shows stored rows or an explicit empty state. It does not invent rows when none are stored.

Live trading is not implemented.

Slogan: TRADE BEYOND LIMITS.

## What is included

- Project configuration, structured logging, and fail-closed execution modes (`READ_ONLY` or `PAPER`).
- A FastAPI health endpoint bound to loopback.
- SQLAlchemy models and the first Alembic revision, applied to local PostgreSQL 17.
- A PySide6 terminal with a black and purple icon rail, a mode badge, and application, database, backend, and GMGN configuration status.
- A read-only GMGN client for market and token research. Trade and signing routes are refused.
- Radar discovery, security, liquidity, indicators, smart-money and whale tag counts, a documented score, rankings, watchlists, and PostgreSQL history.
- A paper execution gateway, order states, position accounting, a strategy registry, and a NautilusTrader 1.231.0 mapping proof.
- CYVORA Shield, which approves or denies paper orders. A paper approval cannot submit a live order.
- Cursor project rules and `AGENTS.md`.

The icon rail lists the operating pages. Radar, Portfolio, CYVORA Intelligence, and Settings stay in the navigation catalog and are not on the rail. Wallet SOL, USD value, and live trading stay unavailable. See [Terminal](docs/terminal/TERMINAL.md).

## Prerequisites

- Windows 11 x64.
- [uv](https://docs.astral.sh/uv/) 0.13 or newer.
- The uv-managed CPython 3.13 already present on this machine, or an equivalent CPython 3.13.
- Git.

PostgreSQL 17 is installed on this PC. Docker and WSL2 are not required. See [Environment](docs/development/ENVIRONMENT.md). The GMGN key belongs in the gitignored `.env` as `GMGN_API_KEY`. Do not add `GMGN_PRIVATE_KEY`.

The Windows `py -3.13` command does not select the uv-managed interpreter on this PC. Use `uv run`.

## Installation

From this directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_dev.ps1
```

`setup_dev.ps1` runs `uv sync --frozen --all-groups`. That creates `.venv` from `uv.lock`. The process-scoped execution-policy flag does not change the system policy.

Copy configuration when you need a database URL or a GMGN key that is not already in `.env`:

```powershell
Copy-Item .env.example .env
```

Do not commit `.env`, and do not paste its values into chat.

## Run

API, on `127.0.0.1:8787`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_api.ps1
```

Desktop:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_desktop.ps1
```

Health check while the API is running:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/health
```

The desktop reports the API as offline when that process is not running. It probes loopback again every 15 seconds. It does not start the API for you.

One bounded supervisor tick, with no GMGN call:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_supervisor.ps1 -Ticks 1
```

A local database dump and a redacted diagnostic file:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\backup_database.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\export_diagnostics.ps1
```

`scripts/register_supervisor_task.ps1` does not register a scheduled task unless you pass `-ConfirmInstall`. The cloud files under `deploy/` are not applied by these commands. See [Operations](docs/operations/OPERATIONS.md).

## Tests

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
```

The script runs Ruff, mypy, pytest, and a desktop smoke launch. The smoke launch opens CYVORA Terminal, checks that the window is visible, and exits. A passing smoke line starts with `CYVORA_DESKTOP_SMOKE_OK`.

## Database

PostgreSQL 17 is installed. `uv run alembic upgrade head` applies revisions through `0007_operations`. A new machine still needs a local role, a database, and `CYVORA_DATABASE_URL` in the untracked `.env`. The URL scheme is `postgresql+psycopg://`. Do not paste the password into chat or into a commit.

One stored radar cycle, when the key and the database are both configured:

```powershell
uv run python scripts/radar_cycle.py
```

The script prints counts, symbols, and `entry=not_authorized`. It does not print the API key or the database URL. The opt-in test is `CYVORA_RADAR_LIVE=1`.

## GMGN

`uv run python scripts/gmgn_readonly_smoke.py` performs the read-only check when `GMGN_API_KEY` is set. It prints shapes, not the key. With no key it prints `GMGN_SMOKE_SKIP` and exits 0. Details are in [GMGN API research](docs/integrations/GMGN_API_RESEARCH.md).

## Security

- The API refuses a non-loopback host.
- `LIVE`, `LIVE_LOCKED`, and `LIVE_AUTHORIZED` are rejected.
- Logs and health payloads omit database passwords, the GMGN key, and exception text that could contain either.
- The GMGN client does not sign and does not submit a transaction.
- Paper orders are simulated records. They do not call a swap or a signer.

Details are in [Security model](docs/security/SECURITY_MODEL.md).

## Troubleshooting

| Symptom | What it means |
|---|---|
| `py -3.13` says no runtime was found | The uv CPython 3.13 install is not registered with the Windows launcher. Use `uv run`. |
| Desktop smoke fails immediately | Read the printed `CYVORA_DESKTOP_SMOKE_FAIL` line and the traceback above it. A missing display plugin is a real failure, not a skipped check. |
| Health database state is `not_configured` | `CYVORA_DATABASE_URL` is empty. On this PC it should be `reachable`. |
| Health database state is `unreachable` | The URL is set and the server did not accept a connection. The driver message is withheld on purpose. |
| `alembic upgrade` stops with `DatabaseNotConfiguredError` | The URL is still unset. Alembic will not invent a database. |

## License

This private repository does not grant an open-source license.
