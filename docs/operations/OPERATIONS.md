# Local operations

Date: 2026-11-11. Phase 8 runs on this PC. It does not install a Windows service, register a scheduled task, or deploy a cloud resource.

## What runs

The API process still binds to loopback. On startup it stops strategies left `RUNNING`, then reads the paper book:

1. Shield control row, or `missing` when the book has never been stored.
2. Paper orders that are not in a terminal state (`CONFIRMED`, `FAILED`, `CANCELLED`, `UNKNOWN`).
3. Open paper positions compared with confirmed fills.
4. Strategies that are still `RUNNING` after the stop pass.

Wallet balances are not read. The recovery row stores `wallet_reconciliation = not_authorized` and `wallet_assumed_flat = false`. A database check constraint rejects any other wallet result. An empty paper book is a real zero count of stored positions. A database that cannot be read leaves the counts unset and blocks new paper entries. A matching book records `complete` and leaves entries open. Shield's own pause is unchanged.

`POST /trading/paper/orders` returns HTTP 409 while `entries_blocked` is true. It does not submit an order. Backtests keep using an isolated ledger.

## Supervisor

`operations.startup` runs five workers for a fixed number of ticks. `--paper-trader` adds a sixth and also enables the radar worker for that process.

| Worker | Tick |
|---|---|
| `radar` | Skipped unless `--include-radar` or `--paper-trader` is set. That calls the existing read-only cycle, including the curl transport and the rate limiter, once per tick. |
| `freshness` | Reads the newest stored radar cycle time. It does not call GMGN. |
| `portfolio` | Counts stored open paper positions. A failed read is not reported as zero. |
| `notifications` | Stores source notices and delivers them locally. Telegram is used only when `CYVORA_TELEGRAM_ENABLED` is set. |
| `paper_strategy` | Evaluates `RUNNING` strategies in `PAPER` mode. An entry is submitted only through Shield, idempotency, and the kill-switch hook, and only when the active profile signal threshold is met. Read-only mode skips the tick. A missing database does not submit an order. |
| `paper_trader` | Present only with `--paper-trader`. It picks stored radar candidates, sizes them from the virtual bankroll, and submits through the same paper broker. Revision `0011_worker_kinds` allows that worker row. See `docs/trading/PAPER_TRADER.md`. |

A tick that raises is retried up to `CYVORA_WORKER_RESTART_LIMIT` (default 2). The exception text is not stored. Heartbeats go to `operation_workers` and `operation_heartbeats` when PostgreSQL is configured. `cloud_deployed` and `live_trading_enabled` are constrained false.

The HTTP route `POST /operations/supervisor/run` accepts 1 to 3 ticks and never sets `--include-radar`.

Bounded run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_supervisor.ps1 -Ticks 1
```

`--ticks 0` repeats until interrupted, with an interval of at least 60 seconds. That process is not started by the desktop and is not registered as a service.

## One session

`scripts/launch_cyvora.ps1` checks that `uv` is on `PATH`, checks that the configured database is a reachable loopback server, runs `alembic upgrade head`, starts the API, and waits for `http://127.0.0.1:<port>/health`. It then opens the desktop. When the desktop exits, it records the stop and ends the API process. `-IncludeSupervisor` also starts `operations.startup --ticks 0` for that session and stops it afterward. `-PaperTrader` adds `--paper-trader` to that supervisor only. Neither switch is the default. The script does not register a scheduled task or a Windows service.

`scripts/launch_cyvora.cmd` calls the same script. `-CreateShortcut` writes a desktop shortcut to the script. That shortcut is not a startup task.

The desktop shows a banner when the API is down or the stored radar cycle is stale. It still does not start the API by itself.

Paper trading from logon is a separate opt-in. The file `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\CYVORA.cmd` starts the API and the supervisor. It does not start the desktop and it is not in the repository. With the paper trader enabled, the supervisor argument is `--ticks 0 --interval-seconds 120 --paper-trader`. Removing `--paper-trader` stops new autonomous entries. Closing the **CYVORA Supervisor** window stops the loop. The kill switch still refuses new paper orders while the process is running. See `docs/trading/PAPER_TRADER.md`.

## Service installation

`scripts/register_supervisor_task.ps1` prints `CYVORA_SERVICE_NOT_INSTALLED` and exits unless `-ConfirmInstall` is present. The template is `deploy/windows/cyvora-supervisor.xml`. The trigger in that file is disabled. Do not pass `-ConfirmInstall` unless you want a persistent logon task on this PC.

`scripts/register_backup_task.ps1` prints `CYVORA_BACKUP_TASK_NOT_INSTALLED` unless `-ConfirmInstall` is present. The planned task runs `uv run python -m operations.backup` daily. It is not registered by the launcher.

## Backup and restore

`scripts/backup_database.ps1` runs `pg_dump` against a loopback server only. The password is passed in the child environment as `PGPASSWORD`, not on the command line. The parent environment is not copied. The tool's own error text is not stored. The dump file name is recorded; the database URL is not. Output goes to `backups/`, which is gitignored.

If `pg_dump` is absent, the status is `tool_missing` and nothing is scheduled to replace it. `pg_restore` and `psql` are accepted only from the same Program Files locations.

A restore always loads the dump into a scratch database first (`cyvora_scratch_<stamp>`). The scratch database is checked for `application_metadata`. The live database is renamed only when the command includes `--swap --confirm SWAP`. The previous database is kept under `cyvora_previous_<stamp>`. A wrong confirmation leaves the live name in place.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore_database.ps1 -File cyvora-20261118T000000Z.dump
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_restore.ps1
```

`verify_restore.ps1` is the restore drill. It uses the newest dump, restores into scratch, and does not swap. Dropping that scratch database requires `--drop-scratch --confirm DROP` on `python -m operations.backup drill`. The drill does not register a task.

## Alerts

The notification worker writes notices for a process stop and for a stored smart-wallet tag count that rose between cycles. It records a local delivery row for notices that are not in the quiet window. Telegram is off unless all of these are set: `CYVORA_TELEGRAM_ENABLED=true`, `CYVORA_TELEGRAM_BOT_TOKEN`, and `CYVORA_TELEGRAM_CHAT_ID`. The token is a secret. It is not printed, not stored in a delivery row, and not included in `repr` or `model_dump`. Sends are limited by `CYVORA_TELEGRAM_BURST` (default 5 per minute) and `CYVORA_TELEGRAM_MIN_INTERVAL_SECONDS` (default 2 between ticks). The Settings checkbox cannot turn the channel on. The preference row stays false.

## Diagnostics

`scripts/export_diagnostics.ps1` writes `diagnostics/cyvora-<timestamp>.json`. The file is redacted with the same rules as the log formatter. The command prints the file name, not the directory. The document does not include the process environment.

## Health and authentication

`/health` remains unauthenticated and still returns status words. It adds worker, stored-cycle, queue, and websocket words. There is no websocket server and no external queue; those cards say so. A stale or missing cycle is the stored timestamp, not a live GMGN call.

Routes other than `/health` still require `CYVORA_API_TOKEN`. Repeated failures in one process return HTTP 429. Accepted, rejected, unconfigured, and limited results can be stored in `auth_events`. That table has no token column.

The desktop probes loopback every 15 seconds after the first check. It does not start the API. The last status stays on screen while the next probe runs. A banner names an API that is down and stored radar data that is stale.

## Retention

`plan_retention` records the market-data window, a log window, and how many backup files to keep. It does not delete anything. `apply_retention` deletes extra `cyvora-*.dump` files, `.log` files older than the log window, and radar-cycle rows older than the market window only when called with `apply=True` or `confirm DELETE`. Audit events and backtests are not deleted. The supervisor does not call it.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\apply_retention.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\apply_retention.ps1 -Confirm
```

The first command prints the plan. `-Confirm` applies it.

## Revision

Alembic revision `0007_operations` creates the worker, heartbeat, recovery, backup, and authentication tables. Revisions `0009_historical_pipeline` through `0012_paper_trader_exited` add the research pipeline and the paper trader. Revision `0013_recovery` adds lifecycle events and delivery rows. Those rows keep `live_trading_enabled` false. The delivery table has no token column.
