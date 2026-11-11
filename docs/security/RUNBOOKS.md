# Runbooks

Date: 2026-11-11. These steps run on the local PC. They do not enable live trading, sign a transaction, or register a Windows service.

The API listens on `127.0.0.1:8787` unless `CYVORA_API_PORT` says otherwise. Routes other than `/health` need `Authorization: Bearer` with `CYVORA_API_TOKEN`. The desktop does not send that token. It reads PostgreSQL on a worker thread.

## Kill switch

Engage when new operator paper orders must stop.

1. Open CYVORA Terminal, Settings, and choose **Engage kill switch**. Confirm the dialog.
2. Or send `POST /operations/kill-switch/engage` with `{"confirm":"ENGAGE"}` and the bearer token.
3. System Health should show the kill switch as `engaged`. `/health` includes the same word and does not include a secret.
4. A new operator paper order is refused. An order that already has the same idempotency key is returned and is not filled again.
5. Pause and resume of paper entries do not change this latch. The analyst cannot release it.

Release only when the operator intends paper evaluation to continue.

1. Settings, **Release kill switch**, and confirm the dialog. Or `POST /operations/kill-switch/release` with `{"confirm":"RELEASE"}`.
2. Shield still evaluates the next paper order. Live trading stays locked.
3. If the database row cannot be read, new operator paper orders stay blocked. Fix PostgreSQL before expecting a release to stick. Do not copy the database URL into a ticket.

The switch does not sell a position and does not submit a chain transaction.

## API or GMGN disconnection

1. Read System Health. `Backend` offline means the desktop cannot reach loopback. The desktop does not start the API. Start it with `uv run cyvora-api` in a separate terminal when the operator wants it.
2. `GMGN` `configured` means a key is present. It does not mean a call succeeded. A radar cycle is the read that contacts GMGN, and only when the operator runs one. The supervisor does not call GMGN unless `--include-radar` is set.
3. Transport failures stay on the GMGN client. They do not create an order. There is no live order to cancel.
4. If health is `degraded`, PostgreSQL was configured and could not be reached. New paper entries that depend on the book stay blocked. The driver text is withheld because it can contain the URL.

## Recovery and an uncertain paper order

1. Run `uv run python -m operations.startup --ticks 1` or `POST /operations/recovery`.
2. Read `entries_blocked`, `wallet_reconciliation`, and `wallet_assumed_flat`. The wallet value stays `not_authorized`. `wallet_assumed_flat` stays false.
3. Do not retry an order whose state is uncertain by sending it again with a new idempotency key. A repeated key returns the stored paper order. A paper `CONFIRMED` state is a simulator result.
4. If recovery says the book is inconsistent or unreadable, leave new paper API entries blocked until the stored orders and positions are understood.

## Backup and diagnostics

1. `uv run python -m operations.backup` writes a custom-format dump under `backups/` for a loopback server only. The command prints the status and the file name. It does not print the URL.
2. `pg_dump` must be the Program Files PostgreSQL binary. A `PATH` copy is ignored.
3. `uv run python -m operations.diagnostics` writes a redacted JSON file under `diagnostics/`. The file is gitignored. Do not attach it to a public issue without reading it first. The export redacts known secrets and database URLs. It does not include the process environment.
4. `uv run python -m readiness` prints the readiness report and `live_trading_enabled=false`.

## Public repository

The GitHub repository is public. Do not paste `.env`, a database URL, an API token, or a wallet secret into an issue, a pull request, or the wiki. `SECURITY.md` states the same rule. Changing the repository to private is an operator decision and is not done by these commands.
