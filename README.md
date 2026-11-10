# CYVORA

CYVORA is a local-first Windows platform for Solana memecoin research, simulation, and, only after a later explicit authorization, supervised trading. This repository is the Phase 1 foundation: a reproducible Python 3.13 environment, a loopback health API, PostgreSQL migration scaffolding, and the CYVORA Terminal shell.

Live trading is not implemented. The desktop does not show market or wallet figures.

Slogan: TRADE BEYOND LIMITS.

## What Phase 1 includes

- Project configuration, structured logging, and fail-closed execution modes (`READ_ONLY` or `PAPER`).
- A FastAPI health endpoint bound to loopback.
- SQLAlchemy models and the first Alembic revision for a local PostgreSQL database.
- A PySide6 terminal with branding, navigation, and real application, database, and backend status.
- Cursor project rules and `AGENTS.md`.

Pages other than Dashboard and System Health are labeled placeholders. They do not contain sample trades.

## Prerequisites

- Windows 11 x64.
- [uv](https://docs.astral.sh/uv/) 0.13 or newer.
- The uv-managed CPython 3.13 already present on this machine, or an equivalent CPython 3.13.
- Git.

PostgreSQL, Docker, and WSL2 are not required to run the Phase 1 shell. PostgreSQL is required before the migration can be applied. See [Environment](docs/development/ENVIRONMENT.md).

The Windows `py -3.13` command does not select the uv-managed interpreter on this PC. Use `uv run`.

## Installation

From this directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_dev.ps1
```

`setup_dev.ps1` runs `uv sync --frozen --all-groups`. That creates `.venv` from `uv.lock`. The process-scoped execution-policy flag does not change the system policy.

Copy configuration only when you are ready to point at a local database:

```powershell
Copy-Item .env.example .env
```

Leave `CYVORA_DATABASE_URL` unset until PostgreSQL is installed. Do not commit `.env`.

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

The desktop reports the API as offline when that process is not running. It does not start the API for you.

## Tests

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
```

The script runs Ruff, mypy, pytest, and a desktop smoke launch. The smoke launch opens CYVORA Terminal, checks that the window is visible, and exits. A passing smoke line starts with `CYVORA_DESKTOP_SMOKE_OK`.

## Database

Phase 1 does not apply migrations automatically, because no PostgreSQL server was installed during setup. After you install PostgreSQL locally:

1. Create a local role and a database.
2. Set `CYVORA_DATABASE_URL` in the untracked `.env` file. Use the `postgresql+psycopg://` scheme.
3. Run `uv run alembic upgrade head`.

Do not paste the database password into chat or into a commit. The manual install step is described in [Environment](docs/development/ENVIRONMENT.md).

## Security

- The API refuses a non-loopback host.
- `LIVE`, `LIVE_LOCKED`, and `LIVE_AUTHORIZED` are rejected.
- Logs and health payloads omit database passwords and exception text that could contain a URL.
- No wallet, GMGN client, or transaction signer is included.

Details are in [Security model](docs/security/SECURITY_MODEL.md).

## Troubleshooting

| Symptom | What it means |
|---|---|
| `py -3.13` says no runtime was found | The uv CPython 3.13 install is not registered with the Windows launcher. Use `uv run`. |
| Desktop smoke fails immediately | Read the printed `CYVORA_DESKTOP_SMOKE_FAIL` line and the traceback above it. A missing display plugin is a real failure, not a skipped check. |
| Health database state is `not_configured` | `CYVORA_DATABASE_URL` is empty. That is the expected Phase 1 state on this PC. |
| Health database state is `unreachable` | The URL is set and the server did not accept a connection. The driver message is withheld on purpose. |
| `alembic upgrade` stops with `DatabaseNotConfiguredError` | The URL is still unset. Alembic will not invent a database. |

## License

This private repository does not grant an open-source license.
