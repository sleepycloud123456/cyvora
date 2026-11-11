# Security review

Date: 2026-11-11. Phase 9 reviewed the code on `main` at `cb11346` and the changes in this phase. This is not a certification, and it does not authorize live trading.

The public repository is `https://github.com/sleepycloud123456/cyvora`. GitHub reports `visibility: public`. `.env` is gitignored and has no commit in history. History mentions `GMGN_PRIVATE_KEY` only as a name the program refuses to load. No private-key block is stored in the tree. Tracked files do not include `.env`, key files, dumps, or logs.

## Findings fixed in this phase

| Area | Finding | Change |
|---|---|---|
| GMGN curl transport | A curl config value is double-quoted. Curl treats `\` inside quotes as an escape, so a trailing backslash could consume the closing quote and turn the rest of the file into options. The API key is in that file. | Backslashes are escaped. Quotes, newlines, and NUL are still refused. The transport also refuses any URL that is not `https://openapi.gmgn.ai` without userinfo, before the config file is written. |
| Settings display | `database_url` is a plain string. `repr` and `model_dump` included the password. A pydantic validation error can also include the rejected input. | The field is omitted from `repr`. `model_dump` says `configured`. `get_settings` re-raises a configuration error that keeps the validator message and drops the input value. |
| Log directory | Backup and diagnostic paths reject `..`. The log directory did not. | `CYVORA_LOG_DIR` rejects a `..` segment. An absolute path is still allowed so tests and an operator-chosen folder work. |
| Local API surface | `/docs`, `/redoc`, and `/openapi.json` were unauthenticated. | Those routes are disabled. `/health` stays open and still returns status words only. |
| Bearer comparison | A very long `Authorization` header was hashed in full. | Values longer than 4096 characters fail the check before the hash. The header is not copied into the 401 body. |
| Database backup | `pg_dump` was taken from `PATH` first, then given `PGPASSWORD`. The child also inherited the operator `PATH`. | Only `C:\Program Files\PostgreSQL\{17,16,15}\bin\pg_dump.exe` and the 32-bit Program Files equivalent are accepted. The child `PATH` is that binary's directory plus `System32`. |
| Kill switch | Pause and resume are a Shield latch. Resume, a strategy, or the analyst could not be the only emergency control, and nothing persisted a separate operator stop. | The kill switch is a separate persisted latch. Resume and the analyst cannot release it. See `docs/security/LIVE_READINESS.md`. |
| Live gate | Live mode names were rejected, but there was no single report of the chain controls that are still absent. | `readiness.live_gate` always returns unauthorized, including when every check is marked present. |

## Findings left open

These are accepted for this phase or they need a decision from the operator. They are not permission to close them by enabling live trading.

- The repository is public. Source, route names, and the fact that a local GMGN key and PostgreSQL exist on this PC are visible. The key and the database URL are not in git. Making the repository private is an operator decision. This phase does not change GitHub settings.
- `/health` has no bearer token. The body is status words, including the kill-switch word, and the socket is loopback.
- Authentication failures are counted in the process for 60 seconds. A restart clears the count. The `auth_events` table does not store the token.
- The desktop reads PostgreSQL on this PC and does not send `CYVORA_API_TOKEN`. Anyone who can run the desktop as this user can pause entries and release the kill switch. The confirmation word is an interlock against a stray click. It is not a second secret.
- `database_url` remains a string inside the process so SQLAlchemy can open it. Code that interpolates that attribute into a log line would publish the password. The CYVORA logger redacts a configured password of at least eight characters and redacts `postgresql://user:password@` text. A shorter password is still covered by the URL pattern.
- An isolated backtest uses an in-memory ledger and does not consult the kill switch. It does not write the operator paper book.
- There is no Solana RPC client, no chain simulation, no chain confirmation, and no wallet balance read. Those are gaps in the readiness report, not missing bugfixes to invent in this phase.
- `pip-audit` on 2026-11-11 reported `fsspec` 2026.2.0, PYSEC-2026-4217, fixed in 2026.6.0. NautilusTrader 1.231.0 requires `fsspec==2026.2.0`, so the lock cannot move without replacing Nautilus. CYVORA does not import `fsspec` or open a reference filesystem. The vulnerable parser runs only when that API is given an attacker-controlled references document. This phase does not change the Nautilus pin.
- A backup still requires PostgreSQL under Program Files. A custom install path is reported as `tool_missing` instead of executing an untrusted binary.
- GitHub issues and the wiki are enabled on the public repository. Do not put secrets in either. `SECURITY.md` says that.

## What was not found

- No route builds SQL from a request string. The `text()` queries use fixed statements or bound parameters.
- No paper path accepts `shield_approved` from the caller. The gateway raises before a store write.
- The GMGN client still refuses `/v1/trade/` and the holdings route before HTTP. The rate limiter is unchanged. Windows reads still use `curl.exe`.
- `GMGN_PRIVATE_KEY` is still not a settings field.
- Container and scheduled-task templates still contain no database URL and no token. Nothing was deployed.
