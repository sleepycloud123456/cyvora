# Phase 1 plan

This is the plan that governed the foundation. Results belong in `PROJECT_STATUS.md`.

## Decisions before coding

- Use the existing `CYVORA` workspace as the repository root.
- Use CPython 3.13.18 through uv. Do not target the default Python 3.15 launcher.
- Do not install NautilusTrader in this phase. Record the stable 1.231.0 Windows wheel and leave 2.0.0rc9 unused.
- Do not install PostgreSQL, Docker, or a cloud database. Build the connection and migration code, and report a missing server honestly.
- Keep the desktop on native Windows. WSL2 cannot start while virtualization is disabled.

## Implementation steps

1. Add ignore rules, `.env.example`, `pyproject.toml`, and the uv lock after resolution.
2. Add settings, logging, domain errors, and the loopback health API.
3. Add the SQLAlchemy metadata model and Alembic revision `0001_application_metadata`.
4. Add the PySide6 shell: theme, sidebar, dashboard status, system health, and placeholders.
5. Add unit tests, a security test for live modes, an integration test that skips when no database URL is set, and a desktop smoke launch.
6. Document versions, decisions, security, cost, and the Cursor workflow.

## Verification

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy`
- `uv run pytest`
- `uv run python -m apps.desktop.main --smoke`
- A real `cyvora-api` process answering `GET /health` on loopback.

## Out of scope

GMGN, wallets, strategies, risk math, paper trading, backtests, notifications, and cloud hosting.
