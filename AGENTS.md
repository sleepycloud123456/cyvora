# AGENTS.md

Permanent instructions for coding agents working on CYVORA. The product is the CYVORA Autonomous Trading Platform. The desktop application is CYVORA Terminal. This file and `.cursor/rules/` outrank chat memory when they disagree with an improvisation. They do not outrank an explicit user instruction or the safety rules below.

## Current phase

Phase 3 is the read-only radar. Do not start Phase 4 (NautilusTrader, strategies, execution), wallet signing, or live execution unless the user explicitly asks and `PROJECT_STATUS.md` shows Phase 3 verified.

The project root is this workspace. Do not create a nested `cyvora/` directory.

## Safety

1. Do not enable or implement real trading.
2. Do not ask for, read, print, or store seed phrases, private keys, or wallet passwords.
3. Do not sign or submit a blockchain transaction.
4. Do not buy services, deploy cloud infrastructure, or add paid APIs.
5. Do not bypass risk limits or authorization checks that already exist.
6. Do not present placeholders, mocks, or sample numbers as GMGN or chain data.
7. Do not invent an API endpoint, adapter, or execution feature.
8. Do not let an AI analyst authorize a financial action. No analyst is implemented in Phase 1.
9. Review a dependency before adding it. Prefer the locked set in `uv.lock`.
10. Do not mark work complete without running it.

Also: do not dump environment variables, do not read `.env`, and do not commit secrets.

## Runtime choices

- Python 3.13 only, via uv. `requires-python` is `>=3.13,<3.14`.
- Install and run with `uv sync --frozen --all-groups` and `uv run`.
- Execution mode is `READ_ONLY` or `PAPER`. Live mode names must keep failing validation.
- The API listens on loopback. The default port is 8787.
- PostgreSQL is the only application database. A missing server is reported as `not_configured` or left unreachable. Do not add SQLite to paper over that.
- NautilusTrader is not a dependency yet. The stable candidate is 1.231.0. Do not install 2.x pre-releases. See `docs/architecture/TECHNICAL_DECISIONS.md`.

## Where code goes

| Area | Path | Phase 1 responsibility |
|---|---|---|
| Desktop | `apps/desktop/` | Terminal shell, theme, status probe |
| API | `apps/api/` | Loopback health application |
| Settings | `config/settings.py` | Environment loading and fail-closed checks |
| Database | `database/` | Engine, models, Alembic revisions |
| Shared types | `domain/` | Modes, errors, status values |
| Operations | `monitoring/` | Logging, redaction, and health collection |
| GMGN | `integrations/gmgn/` | Read-only Agent API client. No signing and no trade calls. |
| Radar | `intelligence/` | Discovery, scoring, and the cycle. No orders. |
| Tests | `tests/` | Unit, security, the optional database check, and the opt-in GMGN and radar smokes |

Do not add empty packages for Shield or strategies until that phase starts.

## Workflow

1. Inspect the files you will change and `PROJECT_STATUS.md`.
2. For a non-trivial change, state the plan, risks, and tests before editing.
3. Keep commits focused. Do not rewrite history unless the user asks.
4. Run Ruff, mypy, pytest, and, for UI changes, `uv run python -m apps.desktop.main --smoke`.
5. Update `PROJECT_STATUS.md` and `CHANGELOG.md` when the behavior or the phase status changes.

Scripts in `scripts/` are the supported Windows entry points. They do not change the machine execution policy.

## Commands

```powershell
uv sync --frozen --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run python -m apps.desktop.main --smoke
uv run cyvora-api
uv run cyvora-desktop
```

## Documentation map

- `README.md` — install and run.
- `PROJECT_STATUS.md` — phase, blockers, and the next action.
- `docs/CURSOR_WORKFLOW.md` — how to continue in Cursor.
- `docs/development/ENVIRONMENT.md` — versions and platform limits.
- `docs/architecture/ARCHITECTURE.md` — what exists now.
- `docs/architecture/TECHNICAL_DECISIONS.md` — choices and tradeoffs.
- `docs/security/SECURITY_MODEL.md` — credentials and fail-closed behavior.
- `docs/ROADMAP.md` — later phases. Phase 3 is not implemented.
- `docs/integrations/GMGN_API_RESEARCH.md` — verified GMGN behavior and the live shapes.
