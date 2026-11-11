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

Sources rechecked on 2026-11-11:

- PyPI project `nautilus_trader`. The newest stable release is 1.231.0. `2.0.0` final is not on PyPI. Pre-releases `2.0.0rc3` through `2.0.0rc9` are present and unused.
- The 1.231.0 wheel `nautilus_trader-1.231.0-cp313-cp313-win_amd64.whl` requires Python `>=3.12,<3.15`.

`uv add nautilus_trader==1.231.0` installed that wheel. `uv run python -c "import nautilus_trader"` prints `1.231.0` on this Windows 11 Home machine. The official CI host is Windows Server 2022, not Windows 11 Home. The mapping and the three offline backtest cases are in `docs/trading/NAUTILUS_MAPPING.md`.

The installed wheel's fixed precision is 9. `uvloop` is not installed; it is not required on Windows.

## PostgreSQL

PostgreSQL 17.11 is installed as the Windows service `postgresql-x64-17`. The service was Running, with start type Automatic, on 2026-11-11. `psql` is not on `PATH`. The binary is `C:\Program Files\PostgreSQL\17\bin\psql.exe`.

A local `cyvora` role and database exist. `CYVORA_DATABASE_URL` is set in the gitignored `.env`. Alembic head is `0004_shield_risk_engine` after Phase 5. The desktop smoke reports the database as `reachable` when the local server answers. Do not print the URL or the password.

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

On 2026-11-11 the same environment also contains `cyvora` 0.8.0 and `nautilus-trader` 1.231.0. Starlette 1.10.0, which FastAPI pulls in, prefers `httpx2` for `TestClient`. Live Windows GMGN calls still use the operating-system curl. The Nautilus transitive pins are in `uv.lock`.
