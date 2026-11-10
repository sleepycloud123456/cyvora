# Cursor workflow

Use this repository as a Cursor project. Grok inside Cursor is the coding agent. Do not add an xAI API key for that; the editor model is separate from a key in `.env`.

## Models

Use the strongest Grok coding model available in the model picker, currently Grok 4.7, for architecture, security, trading logic, and multi-module changes. A faster model is enough for narrow edits once the approach is settled. Keep durable decisions in `AGENTS.md`, `.cursor/rules/`, and `docs/` so a new chat does not depend on the old transcript.

## Start a task

1. Open this folder in Cursor.
2. Read `PROJECT_STATUS.md`, `AGENTS.md`, and the rule files under `.cursor/rules/`.
3. Tell the agent which phase it may touch. Phase 2 and later stay blocked until you say otherwise.
4. Ask for a plan when the change crosses more than one module.

The rules are split on purpose:

| File | Applies |
|---|---|
| `00-cyvora-overview.mdc` | Every session |
| `10-python-engineering.mdc` | Python files |
| `20-security-and-secrets.mdc` | Every session |
| `30-trading-and-risk.mdc` | Every session |
| `40-testing-and-quality.mdc` | Tests |
| `50-cursor-agent-workflow.mdc` | Every session |
| `60-desktop-ui-guidelines.mdc` | Desktop files |

## Run and test

Use the integrated PowerShell terminal. The scripts do not change the system execution policy. If a direct `.\scripts\...` launch is blocked, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_dev.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_desktop.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_api.ps1
```

Review the diff before accepting it. Check that no `.env`, log, or virtual environment was staged. `git status` should not list `uv.lock` as an unexpected change after a normal test run.

## What not to add

- MCP servers for PostgreSQL, GMGN, or Solana. The project calls those systems directly when a later phase needs them.
- A global change to Cursor settings, extensions, or the model list.
- Wallet operations and unrestricted terminal permissions.

## Continue after Phase 1

The next engineering task is not more UI. It is a local PostgreSQL install, then `uv run alembic upgrade head`, then your explicit go-ahead for Phase 2 research. Phase 2 still does not include swaps.
