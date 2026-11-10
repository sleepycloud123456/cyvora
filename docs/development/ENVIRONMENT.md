# Environment

Inspection date: 2026-11-10, with the PostgreSQL and GMGN notes rechecked on 2026-11-11. Commands were run on the project machine. Environment variable values were not printed, and no secret file was read.

## Machine

| Item | Result |
|---|---|
| Operating system | Microsoft Windows 11 Home, version 10.0.26200, build 26200, 64-bit |
| Architecture | AMD64 |
| Git | 2.56.0.windows.4 |
| Remote | `https://github.com/sleepycloud123456/cyvora.git` |
| Node.js | v24.22.1 |
| npm | 11.20.0 |
| uv | 0.13.7 (316c827e0 2026-11-03) |
| pipx | Not installed |
| Docker | `docker` is not recognized |
| psql on PATH | `psql` is not recognized |
| psql installed | `C:\Program Files\PostgreSQL\17\bin\psql.exe`, PostgreSQL 17.11 |
| PostgreSQL service | `postgresql-x64-17`, Running, Automatic |
| WSL | Default version 2 is configured, but WSL2 cannot start because virtualization is not enabled |

Node.js is present and unused. This repository has no JavaScript package. The GMGN client is Python.

## Python interpreters

| Command | Result |
|---|---|
| `py -0p` | 3.15 is the default launcher. 3.12 is registered. 3.13 appears only as `Astral/CPython3.13.18`. |
| `py -3.13 --version` | Failed: `No suitable Python runtime found`. |
| Python 3.15.2 | `C:\Users\Anastasiya\AppData\Local\Python\pythoncore-3.15-64\python.exe`, pip 26.2.2 |
| Python 3.12.10 | `C:\Users\Anastasiya\AppData\Local\Programs\Python\Python312\python.exe`, pip 25.0.1 |
| Python 3.13.18 | `C:\Users\Anastasiya\AppData\Roaming\uv\python\cpython-3.13.18-windows-x86_64-none\python.exe`, pip 26.2.2 |

`import nautilus_trader` failed on 3.12, 3.13, and 3.15 with `ModuleNotFoundError` before this project was created. `import PySide6` also failed on the uv 3.13 interpreter before the project virtual environment was installed.

The project interpreter is 3.13.18. `pyproject.toml` requires `>=3.13,<3.14`, and `.python-version` contains `3.13`. After `uv sync`, `uv python find 3.13` inside this directory resolves to `.venv\Scripts\python.exe`, which is that same 3.13.18.

## NautilusTrader

Sources checked on 2026-11-10:

- Installation guide: https://nautilustrader.io/docs/latest/getting_started/installation/
- PyPI project `nautilus_trader`, stable release 1.231.0.

Findings:

- The stable PyPI release is still 1.x. Version 1.231.0 requires Python `>=3.12,<3.15` and publishes `nautilus_trader-1.231.0-cp313-cp313-win_amd64.whl`.
- PyPI also lists pre-releases `2.0.0rc3` through `2.0.0rc9`. The current documentation describes 2.x and tells installers to pass `--pre`. The project states that 1.x and 2.x Python APIs differ, and that release candidates are not recommended for a production-intended environment.
- Official platform support lists Windows Server 2022 and later, x86_64, tested on `windows-2022`. Windows 11 Home is not in that list. The same guide says other platforms may work but are not the CI targets.
- PyPI wheels target Python 3.13 and 3.14. Python 3.15 needs a source build or a development wheel.
- A dry run of `uv pip install nautilus_trader==1.231.0` with CPython 3.13.18 resolved `nautilus-trader==1.231.0` and 13 dependencies. Nothing from that dry run was installed.
- NautilusTrader is not imported by Phase 1 and is not in `uv.lock`.

## PostgreSQL

PostgreSQL 17.11 is installed as the Windows service `postgresql-x64-17`. The service was Running, with start type Automatic, on 2026-11-11. `psql` is not on `PATH`. The binary is `C:\Program Files\PostgreSQL\17\bin\psql.exe`.

A local `cyvora` role and database exist. `CYVORA_DATABASE_URL` is set in the gitignored `.env`. Alembic current and head are both `0001_application_metadata`. The desktop smoke reports the database as `reachable`. Do not print the URL or the password.

Docker is still not installed. Do not point this project at a hosted database.

## Project virtual environment

`uv sync --all-groups` on 2026-11-10 created `.venv` with CPython 3.13.18 and installed the lockfile. Direct packages:

| Package | Version |
|---|---|
| cyvora | 0.2.0 |
| alembic | 1.20.1 |
| fastapi | 0.162.4 |
| psycopg | 3.3.8 |
| psycopg-binary | 3.3.8 |
| pydantic | 2.14.3 |
| pydantic-settings | 2.16.2 |
| PySide6 | 6.12.0 |
| SQLAlchemy | 2.1.8 |
| uvicorn | 0.54.0 |
| httpx2 | 2.16.0 |
| mypy | 2.4.1 |
| pytest | 9.2.0 |
| pytest-asyncio | 1.4.1.post1 |
| pytest-qt | 4.5.0 |
| ruff | 0.17.4 |

Starlette 1.10.0, which FastAPI pulls in, prefers `httpx2` for `TestClient`. `httpx2` 2.16.0 is also a runtime dependency because the GMGN client uses it for mocked tests and for non-Windows transports. Live Windows calls use the operating-system curl instead. Transitive pins are in `uv.lock`. NautilusTrader is not in the lockfile.
