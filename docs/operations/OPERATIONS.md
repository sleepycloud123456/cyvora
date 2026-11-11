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

`operations.startup` runs four workers for a fixed number of ticks:

| Worker | Tick |
|---|---|
| `radar` | Skipped unless `--include-radar` is set. That flag calls the existing read-only cycle, including the curl transport and the rate limiter. |
| `freshness` | Reads the newest stored radar cycle time. It does not call GMGN. |
| `portfolio` | Counts stored open paper positions. A failed read is not reported as zero. |
| `notifications` | Counts stored local notices. Telegram delivery stays off. |

A tick that raises is retried up to `CYVORA_WORKER_RESTART_LIMIT` (default 2). The exception text is not stored. Heartbeats go to `operation_workers` and `operation_heartbeats` when PostgreSQL is configured. `cloud_deployed` and `live_trading_enabled` are constrained false.

The HTTP route `POST /operations/supervisor/run` accepts 1 to 3 ticks and never sets `--include-radar`.

Bounded run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_supervisor.ps1 -Ticks 1
```

`--ticks 0` repeats until interrupted, with an interval of at least 60 seconds. That process is not started by the desktop and is not registered as a service.

## Service installation

`scripts/register_supervisor_task.ps1` prints `CYVORA_SERVICE_NOT_INSTALLED` and exits unless `-ConfirmInstall` is present. The template is `deploy/windows/cyvora-supervisor.xml`. The trigger in that file is disabled. Do not pass `-ConfirmInstall` unless you want a persistent logon task on this PC.

## Backup

`scripts/backup_database.ps1` runs `pg_dump` against a loopback server only. The password is passed in the child environment as `PGPASSWORD`, not on the command line. The parent environment is not copied. The tool's own error text is not stored. The dump file name is recorded; the database URL is not. Output goes to `backups/`, which is gitignored.

If `pg_dump` is absent, the status is `tool_missing` and nothing is scheduled to replace it.

## Diagnostics

`scripts/export_diagnostics.ps1` writes `diagnostics/cyvora-<timestamp>.json`. The file is redacted with the same rules as the log formatter. The command prints the file name, not the directory. The document does not include the process environment.

## Health and authentication

`/health` remains unauthenticated and still returns status words. It adds worker, stored-cycle, queue, and websocket words. There is no websocket server and no external queue; those cards say so. A stale or missing cycle is the stored timestamp, not a live GMGN call.

Routes other than `/health` still require `CYVORA_API_TOKEN`. Repeated failures in one process return HTTP 429. Accepted, rejected, unconfigured, and limited results can be stored in `auth_events`. That table has no token column.

The desktop probes loopback every 15 seconds after the first check. It does not start the API. The last status stays on screen while the next probe runs.

## Retention

`plan_retention` records the market-data window, a log window, and how many backup files a later cleanup might keep. It does not delete audit events, backtests, or any other rows. No supervisor tick applies it.

## Revision

Alembic revision `0007_operations` creates the worker, heartbeat, recovery, backup, and authentication tables.
