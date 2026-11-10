# Technical decisions

Date: 2026-11-10.

## Project root

The master prompt names the root `cyvora/`. This workspace is already `C:\Users\Anastasiya\CYVORA` and is the Git checkout for `sleepycloud123456/cyvora`. A nested `cyvora` directory would split the repository away from the folder Cursor opened. The workspace is the project root.

## Python 3.13.18

The prompt sets 3.13 as the baseline and says not to select 3.15 only because it is installed.

| Option | Why it was not the runtime |
|---|---|
| 3.15.2, the `py` default | Stable NautilusTrader 1.231.0 requires Python `<3.15`. PyPI has no cp315 wheel. 3.15 would force a source build or a development wheel. |
| 3.12.10 | Usable for Nautilus 1.231.0, but it is older than the requested baseline and a 3.13 interpreter is already installed. |
| 3.14 | The Nautilus 2.x documentation currently suggests 3.14 for PyPI wheels. 3.14 is not installed, and Phase 1 is not adopting the 2.x pre-release those docs describe. |

The uv-managed CPython 3.13.18 is a normal CPython, which matches the Nautilus project's recommendation to use uv with vanilla CPython. `requires-python` is pinned to `>=3.13,<3.14` so a later sync cannot silently move to 3.15.

`py -3.13` does not work because the Windows launcher lists this interpreter as `Astral/CPython3.13.18` rather than as version tag `3.13`. The project uses `uv run` instead of teaching a launcher workaround.

## Dependency manager

uv 0.13.7 is installed and the prompt's tree includes `uv.lock`. uv creates `.venv`, locks direct and transitive versions, and can see the existing 3.13.18 interpreter. pip-tools would be a second resolver beside a tool the machine already has.

## NautilusTrader is not installed yet

Phase 1 does not import or configure the trading engine. Installing a 45 MB native wheel before there is an adapter would not verify the Solana mapping, and the prompt says not to install a release candidate into a production-intended environment without an explicit tradeoff.

Recorded candidate for a later proof of concept:

- Stable package: `nautilus_trader` 1.231.0.
- Wheel: `nautilus_trader-1.231.0-cp313-cp313-win_amd64.whl`.
- A 2026-11-10 dry run on CPython 3.13.18 resolved that version and did not install it.
- Rejected for now: `2.0.0rc9` and every `2.0.0rc*` build. They are pre-releases, and their API is not the 1.x API.

Tradeoff: Phase 4 must re-read the installation page. If 2.0.0 final has shipped by then, the candidate changes and the 1.x notes must not be reused as examples. If the 1.231.0 wheel fails to import on Windows 11 Home, that is new evidence. The official CI host is Windows Server 2022, not Windows 11 Home. WSL2 is not a fallback today: this PC reports that virtualization is disabled, so WSL2 cannot start.

The desktop stays a native PySide6 application either way.

## PySide6 for the shell

The prompt requires PySide6. Version 6.12.0 on PyPI requires Python `>=3.10,<3.16` and publishes a `cp310-abi3` Windows x64 wheel, so it installs on 3.13. The exact locked version is in `uv.lock` after sync. Widgets are the right Phase 1 surface. A separate chart library is deferred until a page actually draws market data.

## FastAPI on loopback

The prompt asks for a FastAPI backend with a health check. One process, one route, and a factory keep the later route table from growing inside the desktop. Uvicorn is the server. The host validator rejects anything except loopback, so the default is not `0.0.0.0`.

Authentication is not attached to `/health` because that response contains no secret and no market data. The security model forbids adding another route without authentication. A fake local token with an empty default would be worse than having no protected route yet.

## PostgreSQL, with no substitute server

The prompt requires PostgreSQL and says not to deploy a cloud database. Docker is not installed, so a compose file would describe a service this machine cannot start. No `docker-compose.yml` is checked in. SQLite is rejected in settings so a later change cannot quietly replace PostgreSQL.

The client library is `psycopg[binary]`. The binary wheel does not need PostgreSQL headers, which are absent along with the server. SQLAlchemy 2 and Alembic own the model and the revision. Financial tables are not created yet; when they are, quantities will be `Numeric`, not binary floats. The metadata timestamp is timezone-aware.

## Desktop status probe

Database and HTTP checks run on a `QThread`. The UI thread only applies a finished snapshot. The probe's exception text is discarded because driver errors can include a URL.

## Logging

The `cyvora` logger writes a fixed text format to stderr and `logs/cyvora.log`. Startup logs whether a database URL is configured, not the URL. Unhandled API errors log the exception type and the path.

## What was left out on purpose

Empty directories for Radar, Shield, strategies, GMGN, Telegram, backtesting, and cloud deployment are not created. The prompt says to create modules when their implementation is scheduled.
