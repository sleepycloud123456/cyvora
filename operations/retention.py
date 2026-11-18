"""Retention windows. Cleanup runs only with an explicit flag or confirmation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from config.settings import Settings
from domain.operations import RetentionPlan, RetentionResult

_DUMP_NAME_PREFIX = "cyvora-"
_DUMP_NAME_SUFFIX = ".dump"
MARKET_CHILD_TABLES = (
    "token_observations",
    "token_analyses",
    "token_candles",
    "security_assessments",
    "liquidity_snapshots",
    "indicator_signals",
    "smart_money_events",
    "whale_events",
)
MARKET_CYCLE_TABLE = "radar_cycles"
_CONFIRM = "DELETE"


def plan_retention(settings: Settings) -> RetentionPlan:
    """Describe retention windows. Nothing is deleted here."""

    return RetentionPlan(
        market_data_days=settings.radar_market_retention_days,
        log_days=settings.log_retention_days,
        backup_files_kept=settings.backup_files_kept,
        audit_events_deleted=False,
        backtests_deleted=False,
        notes=(
            "Audit events are not deleted.",
            "Backtesting datasets are not deleted.",
            "Backup files, old logs, and aged radar cycles are removed only when "
            "apply_retention is called with apply=True or confirm DELETE.",
        ),
    )


def apply_retention(
    settings: Settings,
    *,
    confirm: str | None = None,
    apply: bool = False,
    now: datetime | None = None,
    market_deleter: Callable[[datetime], int] | None = None,
) -> RetentionResult:
    """Remove aged local files and radar cycles when the caller confirms it."""

    allowed = apply or confirm == _CONFIRM
    if not allowed:
        return RetentionResult(
            applied=False,
            backup_files_removed=0,
            log_files_removed=0,
            market_rows_removed=0,
            audit_events_deleted=False,
            backtests_deleted=False,
            detail=(
                "Cleanup did not run. Pass apply=True or confirm DELETE. "
                "Audit events and backtests are not deleted."
            ),
        )
    moment = now or datetime.now(UTC)
    backup_removed = _trim_backups(settings.backup_dir, settings.backup_files_kept)
    log_removed = _trim_logs(settings.log_dir, moment, settings.log_retention_days)
    market_rows = 0
    market_note = ""
    cutoff = moment - timedelta(days=settings.radar_market_retention_days)
    try:
        if market_deleter is not None:
            market_rows = market_deleter(cutoff)
        elif settings.database_url:
            market_rows = delete_expired_market_rows(settings, cutoff)
    except Exception as exc:
        market_note = f" Market cleanup failed ({type(exc).__name__})."
        market_rows = 0
    return RetentionResult(
        applied=True,
        backup_files_removed=backup_removed,
        log_files_removed=log_removed,
        market_rows_removed=market_rows,
        audit_events_deleted=False,
        backtests_deleted=False,
        detail=(
            "Confirmed cleanup finished. Audit events and backtests were not deleted." + market_note
        ),
    )


def delete_expired_market_rows(settings: Settings, cutoff: datetime) -> int:
    """Delete radar rows older than the cutoff. Audit and backtest tables are not named."""

    from sqlalchemy import text

    from database.connection import create_database_engine

    engine = create_database_engine(settings)
    removed = 0
    try:
        with engine.begin() as connection:
            for table in MARKET_CHILD_TABLES:
                result = connection.execute(
                    text(
                        f"DELETE FROM {table} WHERE cycle_id IN "
                        "(SELECT id FROM radar_cycles WHERE finished_at < :cutoff)"
                    ),
                    {"cutoff": cutoff},
                )
                removed += max(0, int(result.rowcount or 0))
            result = connection.execute(
                text(f"DELETE FROM {MARKET_CYCLE_TABLE} WHERE finished_at < :cutoff"),
                {"cutoff": cutoff},
            )
            removed += max(0, int(result.rowcount or 0))
    finally:
        engine.dispose()
    return removed


def _trim_backups(directory: Path, keep: int) -> int:
    if not directory.is_dir():
        return 0
    dumps = [
        path
        for path in directory.iterdir()
        if _safe_file(directory, path)
        and path.name.startswith(_DUMP_NAME_PREFIX)
        and path.name.endswith(_DUMP_NAME_SUFFIX)
    ]
    ordered = sorted(dumps, key=lambda path: path.name)
    extra = ordered[:-keep] if keep > 0 else ordered
    removed = 0
    for path in extra:
        path.unlink()
        removed += 1
    return removed


def _trim_logs(directory: Path, now: datetime, days: int) -> int:
    if not directory.is_dir():
        return 0
    cutoff = now.timestamp() - (days * 86400)
    removed = 0
    for path in directory.iterdir():
        if not _safe_file(directory, path) or path.suffix != ".log":
            continue
        if path.stat().st_mtime >= cutoff:
            continue
        path.unlink()
        removed += 1
    return removed


def _safe_file(root: Path, candidate: Path) -> bool:
    if not candidate.is_file() or candidate.is_symlink():
        return False
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return candidate.parent.resolve() == root.resolve()


def main(argv: list[str] | None = None) -> None:
    """Print the plan, or apply it when --apply or --confirm DELETE is present."""

    import argparse

    from config.settings import assert_runtime_safe, get_settings

    parser = argparse.ArgumentParser(prog="cyvora-retention")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    settings = get_settings()
    assert_runtime_safe(settings)
    if not args.apply and args.confirm != _CONFIRM:
        plan = plan_retention(settings)
        print("CYVORA_RETENTION_PLAN")
        print("applied=false")
        print(f"backup_files_kept={plan.backup_files_kept}")
        print(f"log_days={plan.log_days}")
        print(f"market_data_days={plan.market_data_days}")
        print("audit_events_deleted=false")
        print("backtests_deleted=false")
        print("live_trading_enabled=false")
        raise SystemExit(0)
    result = apply_retention(
        settings,
        confirm=args.confirm or None,
        apply=bool(args.apply),
    )
    print("CYVORA_RETENTION_APPLIED" if result.applied else "CYVORA_RETENTION_PLAN")
    print(f"applied={str(result.applied).lower()}")
    print(f"backup_files_removed={result.backup_files_removed}")
    print(f"log_files_removed={result.log_files_removed}")
    print(f"market_rows_removed={result.market_rows_removed}")
    print("audit_events_deleted=false")
    print("backtests_deleted=false")
    print("live_trading_enabled=false")
    raise SystemExit(0 if result.applied else 1)


if __name__ == "__main__":
    main()
