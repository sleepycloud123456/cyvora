"""Restore a local dump into a scratch database before any optional swap."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from config.settings import Settings
from domain.operations import RestoreReport
from operations.backup import _child_env, _target, find_pg_tool

_DUMP_NAME = re.compile(r"^cyvora-\d{8}T\d{6}Z\.dump$")
_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
Runner = Callable[[list[str], Mapping[str, str]], "CommandResult"]


@dataclass(frozen=True, slots=True)
class CommandResult:
    """A tool result. stdout is not written to the report."""

    code: int
    stdout: str = ""


def run_restore(
    settings: Settings,
    file_name: str,
    *,
    swap: bool = False,
    confirm: str | None = None,
    now: datetime | None = None,
    tool: Path | None = None,
    psql: Path | None = None,
    runner: Runner | None = None,
) -> RestoreReport:
    """Restore into a scratch database. Swap only when confirm is SWAP."""

    started = now or datetime.now(UTC)
    if not settings.database_url:
        return _finish(
            "not_configured",
            "pg_restore",
            None,
            None,
            None,
            False,
            False,
            "CYVORA_DATABASE_URL is not set. No restore ran.",
            started,
        )
    parsed = _target(settings.database_url)
    if parsed is None:
        return _finish(
            "refused",
            "pg_restore",
            None,
            None,
            None,
            False,
            False,
            "Restores only run against a loopback PostgreSQL server.",
            started,
        )
    host, port, user, password, database = parsed
    if not _IDENT.fullmatch(database):
        return _finish(
            "refused",
            "pg_restore",
            None,
            None,
            None,
            False,
            False,
            "The database name must be a lowercase identifier. No restore ran.",
            started,
        )
    safe_name = _dump_name(file_name)
    if safe_name is None:
        return _finish(
            "refused",
            "pg_restore",
            None,
            None,
            None,
            False,
            False,
            "The dump name is not a CYVORA backup file. No restore ran.",
            started,
        )
    dump_path = _dump_path(settings, safe_name)
    if dump_path is None:
        return _finish(
            "refused",
            "pg_restore",
            safe_name,
            None,
            None,
            False,
            False,
            "The dump file is not in the backup directory. No restore ran.",
            started,
        )
    restore_bin = tool if tool is not None else find_pg_tool("pg_restore.exe")
    psql_bin = psql if psql is not None else find_pg_tool("psql.exe")
    if restore_bin is None or psql_bin is None:
        return _finish(
            "tool_missing",
            "pg_restore",
            safe_name,
            None,
            None,
            False,
            False,
            "pg_restore or psql was not found. No restore ran and no task was scheduled.",
            started,
        )
    stamp = safe_name.removeprefix("cyvora-").removesuffix(".dump").lower()
    scratch = f"cyvora_scratch_{stamp}"
    previous = f"cyvora_previous_{stamp}"
    if not _IDENT.fullmatch(scratch) or not _IDENT.fullmatch(previous):
        return _finish(
            "refused",
            "pg_restore",
            safe_name,
            None,
            None,
            False,
            False,
            "The scratch database name was rejected. No restore ran.",
            started,
        )
    if database in {scratch, previous, "postgres"}:
        return _finish(
            "refused",
            "pg_restore",
            safe_name,
            scratch,
            None,
            False,
            False,
            "The live database name cannot be replaced by this restore.",
            started,
        )
    execute = runner or _subprocess
    maintenance = _child_env(host, port, user, password, "postgres", psql_bin)
    created = _invoke(
        execute,
        [str(psql_bin), "--no-password", "--command", f"CREATE DATABASE {scratch}"],
        maintenance,
    )
    if created.code != 0:
        return _finish(
            "failed",
            psql_bin.name,
            safe_name,
            scratch,
            None,
            False,
            False,
            "The scratch database was not created. The live database was not changed.",
            started,
            now,
        )
    restored = _invoke(
        execute,
        [str(restore_bin), "--format=custom", "--no-password", "--exit-on-error", str(dump_path)],
        _child_env(host, port, user, password, scratch, restore_bin),
    )
    if restored.code != 0:
        return _finish(
            "failed",
            restore_bin.name,
            safe_name,
            scratch,
            None,
            False,
            False,
            "pg_restore failed. The live database was not changed. The tool message was withheld.",
            started,
            now,
        )
    verified = _invoke(
        execute,
        [
            str(psql_bin),
            "--no-password",
            "--tuples-only",
            "--no-align",
            "--command",
            "SELECT CASE WHEN to_regclass('public.application_metadata') IS NULL "
            "THEN 'missing' ELSE 'present' END",
        ],
        _child_env(host, port, user, password, scratch, psql_bin),
    )
    if verified.code != 0 or verified.stdout.strip() != "present":
        return _finish(
            "failed",
            psql_bin.name,
            safe_name,
            scratch,
            None,
            False,
            False,
            "The scratch database did not contain application metadata. "
            "The live database was not changed.",
            started,
            now,
        )
    if not swap:
        return _finish(
            "verified",
            restore_bin.name,
            safe_name,
            scratch,
            None,
            False,
            False,
            "The dump was restored into a scratch database. The live database was not changed.",
            started,
            now,
        )
    if confirm != "SWAP":
        return _finish(
            "verified",
            restore_bin.name,
            safe_name,
            scratch,
            None,
            False,
            False,
            "Swap was not confirmed, so the live database was left in place.",
            started,
            now,
        )
    renamed = _swap(execute, psql_bin, maintenance, database, scratch, previous)
    if not renamed:
        return _finish(
            "failed",
            psql_bin.name,
            safe_name,
            scratch,
            previous,
            False,
            False,
            "The scratch database was verified. The swap did not finish. "
            "The tool message was withheld.",
            started,
            now,
        )
    return _finish(
        "swapped",
        restore_bin.name,
        safe_name,
        scratch,
        previous,
        True,
        False,
        "The verified scratch database replaced the live name. The previous name was kept.",
        started,
        now,
    )


def run_restore_drill(
    settings: Settings,
    *,
    file_name: str | None = None,
    drop_scratch: bool = False,
    confirm: str | None = None,
    now: datetime | None = None,
    tool: Path | None = None,
    psql: Path | None = None,
    runner: Runner | None = None,
) -> RestoreReport:
    """Restore the newest dump into scratch and verify it. The live name is not swapped."""

    selected = file_name or newest_dump(settings.backup_dir)
    if selected is None:
        started = now or datetime.now(UTC)
        return _finish(
            "refused",
            "pg_restore",
            None,
            None,
            None,
            False,
            False,
            "No dump file is available for the restore drill.",
            started,
        )
    report = run_restore(
        settings,
        selected,
        swap=False,
        now=now,
        tool=tool,
        psql=psql,
        runner=runner,
    )
    if report.status != "verified" or not drop_scratch or report.scratch_database is None:
        return report
    if confirm != "DROP":
        return RestoreReport(
            status=report.status,
            tool=report.tool,
            file_name=report.file_name,
            scratch_database=report.scratch_database,
            previous_database=None,
            swapped=False,
            scratch_dropped=False,
            detail="The scratch database was verified and left in place. Drop was not confirmed.",
            started_at=report.started_at,
            finished_at=report.finished_at,
            live_trading_enabled=False,
        )
    parsed = None if settings.database_url is None else _target(settings.database_url)
    psql_bin = psql if psql is not None else find_pg_tool("psql.exe")
    if parsed is None or psql_bin is None:
        return report
    host, port, user, password, _database = parsed
    execute = runner or _subprocess
    dropped = _drop_scratch(
        execute,
        psql_bin,
        _child_env(host, port, user, password, "postgres", psql_bin),
        report.scratch_database,
    )
    return RestoreReport(
        status="verified" if dropped else "failed",
        tool=report.tool,
        file_name=report.file_name,
        scratch_database=report.scratch_database,
        previous_database=None,
        swapped=False,
        scratch_dropped=dropped,
        detail=(
            "The scratch database was verified and dropped."
            if dropped
            else "The scratch database was verified. Dropping it failed. The live database "
            "was not changed."
        ),
        started_at=report.started_at,
        finished_at=datetime.now(UTC) if now is None else now,
        live_trading_enabled=False,
    )


def newest_dump(directory: Path) -> str | None:
    """Return the newest CYVORA dump name in the backup directory."""

    if not directory.is_dir():
        return None
    names = [
        path.name
        for path in directory.iterdir()
        if path.is_file() and not path.is_symlink() and _DUMP_NAME.fullmatch(path.name)
    ]
    if not names:
        return None
    return sorted(names)[-1]


def _swap(
    execute: Runner,
    psql_bin: Path,
    maintenance: Mapping[str, str],
    database: str,
    scratch: str,
    previous: str,
) -> bool:
    terminated = _invoke(
        execute,
        [
            str(psql_bin),
            "--no-password",
            "--command",
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{database}' AND pid <> pg_backend_pid()",
        ],
        maintenance,
    )
    if terminated.code != 0:
        return False
    renamed = _invoke(
        execute,
        [
            str(psql_bin),
            "--no-password",
            "--command",
            f"ALTER DATABASE {database} RENAME TO {previous}",
        ],
        maintenance,
    )
    if renamed.code != 0:
        return False
    swapped = _invoke(
        execute,
        [
            str(psql_bin),
            "--no-password",
            "--command",
            f"ALTER DATABASE {scratch} RENAME TO {database}",
        ],
        maintenance,
    )
    if swapped.code == 0:
        return True
    _invoke(
        execute,
        [
            str(psql_bin),
            "--no-password",
            "--command",
            f"ALTER DATABASE {previous} RENAME TO {database}",
        ],
        maintenance,
    )
    return False


def _drop_scratch(
    execute: Runner,
    psql_bin: Path,
    maintenance: Mapping[str, str],
    scratch: str,
) -> bool:
    if not _IDENT.fullmatch(scratch) or not scratch.startswith("cyvora_scratch_"):
        return False
    terminated = _invoke(
        execute,
        [
            str(psql_bin),
            "--no-password",
            "--command",
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{scratch}' AND pid <> pg_backend_pid()",
        ],
        maintenance,
    )
    if terminated.code != 0:
        return False
    dropped = _invoke(
        execute,
        [str(psql_bin), "--no-password", "--command", f"DROP DATABASE IF EXISTS {scratch}"],
        maintenance,
    )
    return dropped.code == 0


def _dump_name(file_name: str) -> str | None:
    name = Path(file_name).name
    if name != file_name or _DUMP_NAME.fullmatch(name) is None:
        return None
    return name


def _dump_path(settings: Settings, file_name: str) -> Path | None:
    root = settings.backup_dir.resolve()
    candidate = (settings.backup_dir / file_name).resolve()
    if candidate.parent != root or not candidate.is_file() or candidate.is_symlink():
        return None
    return candidate


def _invoke(execute: Runner, argv: list[str], env: Mapping[str, str]) -> CommandResult:
    try:
        return execute(argv, env)
    except OSError:
        return CommandResult(127, "")


def _subprocess(argv: list[str], env: Mapping[str, str]) -> CommandResult:
    import subprocess

    completed = subprocess.run(argv, env=dict(env), capture_output=True, check=False)
    stdout = completed.stdout.decode("utf-8", errors="replace") if completed.stdout else ""
    return CommandResult(int(completed.returncode), stdout.strip())


def _finish(
    status: str,
    tool: str,
    file_name: str | None,
    scratch_database: str | None,
    previous_database: str | None,
    swapped: bool,
    scratch_dropped: bool,
    detail: str,
    started: datetime,
    now: datetime | None = None,
) -> RestoreReport:
    return RestoreReport(
        status=status,
        tool=tool,
        file_name=file_name,
        scratch_database=scratch_database,
        previous_database=previous_database,
        swapped=swapped,
        scratch_dropped=scratch_dropped,
        detail=detail,
        started_at=started,
        finished_at=now or datetime.now(UTC),
        live_trading_enabled=False,
    )
