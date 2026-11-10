# Project status

Date: 2026-11-10.

## Current phase

Phase 1 — Development environment and foundation. The definition of done is met for everything that can run on this PC. PostgreSQL is not installed, so the migration has not been applied.

## Current milestone

CYVORA Terminal starts, the loopback health API answers, and the locked Python 3.13 environment reproduces from `uv.lock`.

## Completed work

- Inspected Windows, Python, uv, Git, Node, PostgreSQL, Docker, and WSL without printing environment values.
- Chose CPython 3.13.18. Left Python 3.15 and NautilusTrader 2.0.0rc9 unused.
- Added the package, lockfile, `.env.example`, ignore rules, and PowerShell scripts.
- Added settings, logging, the health API, the `application_metadata` migration, and the terminal shell.
- Added Cursor rules, `AGENTS.md`, and the Phase 1 docs.

## In progress

Nothing inside Phase 1. Phase 2 has not started.

## Blockers

PostgreSQL is not installed, and Docker cannot replace it because Docker is not installed and WSL2 cannot start. This does not block the shell or the API. It blocks `alembic upgrade head`.

## Tests

Final run after the navigation bug fix:

- `uv run ruff check .` — passed.
- `uv run ruff format --check .` — 63 files already formatted.
- `uv run mypy` — no issues in 38 source files.
- `uv run pytest -rs` — 29 passed, 1 skipped.
- Skip: `tests/integration/test_database_connectivity.py` — `CYVORA_DATABASE_URL is not set, so PostgreSQL was not contacted.`
- Desktop smoke: `CYVORA_DESKTOP_SMOKE_OK python=3.13.18 mode=READ-ONLY database=not_configured backend=offline`
- Live API on `127.0.0.1:8799`: `GET /health` returned HTTP 200 with `live_trading_enabled: false`, database `not_configured`, and backend `running`. `GET /orders` returned HTTP 404. The process was then stopped.

Pytest found and the code fix covered a real startup bug: the sidebar selected its first item before the content widgets existed, so `page_title` was missing. The content is now built first. No test is left failing.

## Known limitations

- NautilusTrader 1.231.0 has a `cp313` `win_amd64` wheel and resolved in a dry run. It was not installed or imported. Official CI is Windows Server 2022, not Windows 11 Home.
- NautilusTrader 2.0.0rc9 is a pre-release and is not a dependency. The 1.x and 2.x Python APIs differ.
- `py -3.13` does not find the uv interpreter. Use `uv run`.
- WSL2 is installed as the default version but cannot start until virtualization is enabled. It is not required for Phase 1.
- The terminal shows placeholders for every page except Dashboard and System Health. Those placeholders do not contain market data.
- `/health` is unauthenticated. Its body is process status only, and the socket is loopback.

## Security

- Live mode names are rejected.
- No wallet, GMGN, or transaction code exists.
- Database passwords are redacted and driver errors are not returned.
- `.env` is gitignored. No `.env` file was created.

## Exact next actions

1. Install PostgreSQL 16 or 17 for Windows x64.
2. Create a local role and database. Put the URL in an untracked `.env` copied from `.env.example`. Do not paste the password into chat.
3. Run `uv run alembic upgrade head`.
4. Ask for Phase 2 only after that, if GMGN read-only research is the next goal. Phase 2 still does not include swaps.

## Phase 1 checklist

| Done criterion | Result |
|---|---|
| Project exists | This repository |
| Environment documented | `docs/development/ENVIRONMENT.md` |
| Virtual environment works | `.venv`, CPython 3.13.18 |
| Dependencies reproducible | `uv.lock` |
| Cursor instructions exist | `AGENTS.md`, `.cursor/rules/` |
| Minimal application launches | Desktop smoke and live `/health` |
| Basic tests pass | 29 passed, 1 skipped |
| Platform limits recorded | This file and the environment doc |
| Status updated | This file |
