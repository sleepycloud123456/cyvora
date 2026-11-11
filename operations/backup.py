"""Local PostgreSQL dumps. The password is not placed on the command line."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from config.settings import Settings
from domain.operations import BackupReport

_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
Runner = Callable[[list[str], Mapping[str, str], Path], int]


def find_pg_dump() -> Path | None:
    """Return a local pg_dump binary, or None when it is not installed."""

    found = shutil.which("pg_dump")
    if found:
        return Path(found)
    for candidate in (
        Path(r"C:\Program Files\PostgreSQL\17\bin\pg_dump.exe"),
        Path(r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"),
    ):
        if candidate.is_file():
            return candidate
    return None


def run_backup(
    settings: Settings,
    *,
    now: datetime | None = None,
    tool: Path | None = None,
    runner: Runner | None = None,
) -> BackupReport:
    """Dump the local database into the workspace backup directory.

    The destination file name is returned. The database URL is not.
    """

    started = now or datetime.now(UTC)
    if not settings.database_url:
        return _finish(
            "not_configured",
            "pg_dump",
            None,
            None,
            "CYVORA_DATABASE_URL is not set. No dump was created.",
            started,
        )
    parsed = _target(settings.database_url)
    if parsed is None:
        return _finish(
            "refused",
            "pg_dump",
            None,
            None,
            "Backups only run against a loopback PostgreSQL server.",
            started,
        )
    host, port, user, password, database = parsed
    binary = tool if tool is not None else find_pg_dump()
    if binary is None:
        return _finish(
            "tool_missing",
            "pg_dump",
            None,
            None,
            "pg_dump was not found. No dump was created and no task was scheduled.",
            started,
        )
    directory = settings.backup_dir
    directory.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    file_name = f"cyvora-{stamp}.dump"
    destination = directory / file_name
    argv = [
        str(binary),
        "--format=custom",
        "--no-password",
        "--file",
        str(destination),
    ]
    env = _child_env(host, port, user, password, database)
    execute = runner or _subprocess
    try:
        code = execute(argv, env, destination)
    except OSError:
        return _finish(
            "failed",
            binary.name,
            None,
            None,
            "pg_dump could not be started. The command text was withheld.",
            started,
            now,
        )
    if code != 0 or not destination.is_file():
        if destination.is_file():
            destination.unlink(missing_ok=True)
        return _finish(
            "failed",
            binary.name,
            None,
            None,
            "pg_dump failed. The tool message was withheld because it can contain the URL.",
            started,
            now,
        )
    return _finish(
        "completed",
        binary.name,
        file_name,
        destination.stat().st_size,
        "A local custom-format dump was written. The database URL was not stored.",
        started,
        now,
    )


def _target(url: str) -> tuple[str, int, str, str | None, str] | None:
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = parts.hostname or ""
    if host not in _LOOPBACK:
        return None
    database = parts.path.lstrip("/")
    if not database or not parts.username:
        return None
    port = 5432 if parts.port is None else parts.port
    return host, port, parts.username, parts.password, database


def _child_env(
    host: str, port: int, user: str, password: str | None, database: str
) -> dict[str, str]:
    """Pass pg_dump the connection fields and the Windows process paths.

    The parent environment is not copied, so unrelated secrets are not given
    to the dump process.
    """

    env = {
        key: os.environ[key]
        for key in ("SYSTEMROOT", "SystemRoot", "PATH", "PATHEXT", "COMSPEC", "WINDIR")
        if key in os.environ
    }
    env["PGHOST"] = host
    env["PGPORT"] = str(port)
    env["PGUSER"] = user
    env["PGDATABASE"] = database
    if password is not None:
        env["PGPASSWORD"] = password
    return env


def _subprocess(argv: list[str], env: Mapping[str, str], destination: Path) -> int:
    del destination
    completed = subprocess.run(argv, env=dict(env), capture_output=True, check=False)
    return int(completed.returncode)


def main() -> None:
    """Create one local dump and print only the status, tool, and file name."""

    from config.settings import assert_runtime_safe, get_settings

    settings = get_settings()
    assert_runtime_safe(settings)
    report = run_backup(settings)
    if settings.database_url and report.status == "completed":
        try:
            from database.repositories.operations import PostgresOperationsRepository

            PostgresOperationsRepository(settings).save_backup(report)
        except Exception as exc:
            print(f"CYVORA_BACKUP_RECORD_FAIL error_type={type(exc).__name__}")
    print(f"CYVORA_BACKUP_{report.status.upper()}")
    print(f"tool={report.tool}")
    print(f"file={report.file_name or 'none'}")
    size = "none" if report.size_bytes is None else str(report.size_bytes)
    print(f"bytes={size}")
    print("live_trading_enabled=false")
    raise SystemExit(0 if report.status in {"completed", "not_configured", "tool_missing"} else 1)


def _finish(
    status: str,
    tool: str,
    file_name: str | None,
    size_bytes: int | None,
    detail: str,
    started: datetime,
    now: datetime | None = None,
) -> BackupReport:
    return BackupReport(
        status=status,
        tool=tool,
        file_name=file_name,
        size_bytes=size_bytes,
        detail=detail,
        started_at=started,
        finished_at=now or datetime.now(UTC),
        live_trading_enabled=False,
    )


if __name__ == "__main__":
    main()
