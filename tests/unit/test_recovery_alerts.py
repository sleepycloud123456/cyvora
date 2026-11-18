"""Restore, retention, and notice delivery. These tests do not call Telegram or PostgreSQL."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from config.settings import Settings
from domain.operations import TickResult
from domain.terminal import AlertEvidence, NotificationDraft, NotificationPreferences
from operations.alerts import (
    ProcessEvent,
    SmartMoneySample,
    accumulation_events,
    application_stopped_events,
)
from operations.delivery import PendingNotice, deliver_notices, send_allowed
from operations.restore import CommandResult, run_restore, run_restore_drill
from operations.retention import MARKET_CHILD_TABLES, MARKET_CYCLE_TABLE, apply_retention
from operations.workers import NotificationWorker

NOW = datetime(2026, 11, 11, tzinfo=UTC)
PASSWORD = "dump-secret-value"
TOKEN = "123456789:telegram-test-token"
MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


class MemoryStorage:
    """In-memory notice rows for the delivery worker."""

    def __init__(self, prior: tuple[datetime, ...] = ()) -> None:
        self.prior = prior
        self.inserted: list[NotificationDraft] = []
        self.records: list[tuple[str, str, str, str]] = []
        self.rows = (
            PendingNotice(
                "stop-1",
                "application_stopped",
                "launcher",
                "The launcher stopped the local processes.",
                False,
                False,
                None,
            ),
            PendingNotice(
                "score-1",
                "high_score",
                MINT,
                "Stored as approved for further analysis. That is not an entry.",
                False,
                False,
                None,
            ),
        )

    def alerts(self) -> tuple[AlertEvidence, ...]:
        return (
            AlertEvidence(
                "application_stopped",
                "api",
                "The API process stopped.",
                NOW,
            ),
        )

    def preferences(self) -> NotificationPreferences:
        from terminal.profiles import default_preferences

        return default_preferences()

    def pending(self) -> tuple[PendingNotice, ...]:
        return self.rows

    def prior_telegram(self, now: datetime) -> tuple[datetime, ...]:
        del now
        return self.prior

    def insert_notices(self, drafts: tuple[NotificationDraft, ...], now: datetime) -> int:
        del now
        self.inserted.extend(drafts)
        return len(drafts)

    def record(
        self,
        dedup_key: str,
        channel: str,
        status: str,
        detail: str,
        now: datetime,
    ) -> None:
        del now
        self.records.append((dedup_key, channel, status, detail))


def test_accumulation_requires_a_stored_increase_and_stops_are_sourced() -> None:
    flat = (
        SmartMoneySample(MINT, "AAA", 1, 2, NOW),
        SmartMoneySample(MINT, "AAA", 2, 2, NOW),
    )
    assert accumulation_events(flat) == ()
    rising = accumulation_events(
        (
            SmartMoneySample(MINT, "AAA", 1, 2, NOW),
            SmartMoneySample(MINT, "AAA", 2, 5, NOW + timedelta(minutes=5)),
        )
    )
    assert rising[0].category == "smart_money_accumulation"
    assert "2" in rising[0].detail and "5" in rising[0].detail
    assert "not an entry" in rising[0].detail
    stopped = application_stopped_events(
        (
            ProcessEvent("launcher", "started", "The launcher started the local processes.", NOW),
            ProcessEvent("launcher", "stopped", "The launcher stopped the local processes.", NOW),
        )
    )
    assert len(stopped) == 1
    assert stopped[0].category == "application_stopped"
    hidden = application_stopped_events(
        (ProcessEvent("api", "stopped", "postgresql://cyvora:secret@127.0.0.1/cyvora", NOW),)
    )
    assert "secret" not in hidden[0].detail


def test_restore_checks_a_scratch_database_before_swap(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    backup = tmp_path / "backups"
    backup.mkdir()
    dump = backup / "cyvora-20261111T000000Z.dump"
    dump.write_bytes(b"PGDMP")
    settings = _settings(tmp_path)
    calls: list[str] = []

    def runner(argv: list[str], env: dict[str, str]) -> CommandResult:
        joined = " ".join(argv)
        calls.append(joined)
        assert PASSWORD not in joined
        assert "PGPASSWORD" not in joined
        assert env["PGPASSWORD"] == PASSWORD
        if "to_regclass" in joined:
            return CommandResult(0, "present")
        return CommandResult(0, "")

    held = run_restore(
        settings,
        dump.name,
        swap=True,
        confirm="NO",
        now=NOW,
        tool=Path("pg_restore.exe"),
        psql=Path("psql.exe"),
        runner=runner,
    )
    assert held.status == "verified"
    assert held.swapped is False
    assert held.scratch_database == "cyvora_scratch_20261111t000000z"
    assert PASSWORD not in held.detail
    assert not any("ALTER DATABASE" in call for call in calls)
    assert any("CREATE DATABASE cyvora_scratch_20261111t000000z" in call for call in calls)

    calls.clear()
    swapped = run_restore(
        settings,
        dump.name,
        swap=True,
        confirm="SWAP",
        now=NOW,
        tool=Path("pg_restore.exe"),
        psql=Path("psql.exe"),
        runner=runner,
    )
    assert swapped.status == "swapped"
    assert swapped.swapped is True
    assert swapped.previous_database == "cyvora_previous_20261111t000000z"
    assert swapped.live_trading_enabled is False
    create_at = next(index for index, call in enumerate(calls) if "CREATE DATABASE" in call)
    swap_at = next(index for index, call in enumerate(calls) if "ALTER DATABASE" in call)
    assert create_at < swap_at
    assert PASSWORD not in swapped.detail


def test_restore_drill_does_not_swap_or_drop_without_confirmation(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    backup = tmp_path / "backups"
    backup.mkdir()
    (backup / "cyvora-20261111T000000Z.dump").write_bytes(b"PGDMP")
    calls: list[str] = []

    def runner(argv: list[str], env: dict[str, str]) -> CommandResult:
        del env
        joined = " ".join(argv)
        calls.append(joined)
        if "to_regclass" in joined:
            return CommandResult(0, "present")
        return CommandResult(0, "")

    report = run_restore_drill(
        _settings(tmp_path),
        now=NOW,
        tool=Path("pg_restore.exe"),
        psql=Path("psql.exe"),
        runner=runner,
    )
    assert report.status == "verified"
    assert report.swapped is False
    assert report.scratch_dropped is False
    assert not any("DROP DATABASE" in call or "ALTER DATABASE" in call for call in calls)


def test_restore_refuses_a_remote_database(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        log_dir=tmp_path,
        database_url=f"postgresql+psycopg://cyvora:{PASSWORD}@example.com:5432/cyvora",
    )
    report = run_restore(settings, "cyvora-20261111T000000Z.dump", now=NOW)
    assert report.status == "refused"
    assert report.swapped is False
    assert PASSWORD not in report.detail


def test_retention_cleanup_runs_only_with_an_explicit_flag(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    backup = tmp_path / "backups"
    logs = tmp_path / "logs"
    backup.mkdir()
    logs.mkdir()
    old = backup / "cyvora-20200101T000000Z.dump"
    kept = backup / "cyvora-20261111T000000Z.dump"
    old.write_bytes(b"old")
    kept.write_bytes(b"new")
    (backup / "notes.txt").write_text("keep", encoding="utf-8")
    old_log = logs / "cyvora.log"
    old_log.write_text("log", encoding="utf-8")
    os.utime(old_log, (time.time() - 86400 * 40, time.time() - 86400 * 40))
    settings = Settings(
        _env_file=None,
        log_dir=Path("logs"),
        backup_dir=Path("backups"),
        backup_files_kept=1,
        log_retention_days=14,
    )
    calls = {"count": 0}

    def deleter(cutoff: datetime) -> int:
        del cutoff
        calls["count"] += 1
        return 4

    skipped = apply_retention(settings, confirm="delete", now=NOW, market_deleter=deleter)
    assert skipped.applied is False
    assert calls["count"] == 0
    assert old.exists() and kept.exists() and old_log.exists()
    applied = apply_retention(settings, apply=True, now=NOW, market_deleter=deleter)
    assert applied.applied is True
    assert applied.backup_files_removed == 1
    assert applied.log_files_removed == 1
    assert applied.market_rows_removed == 4
    assert applied.audit_events_deleted is False
    assert applied.backtests_deleted is False
    assert not old.exists()
    assert kept.exists()
    assert (backup / "notes.txt").exists()
    assert not old_log.exists()
    assert "audit_events" not in MARKET_CHILD_TABLES
    assert "simulation" not in MARKET_CYCLE_TABLE
    assert all("audit" not in name and "simulation" not in name for name in MARKET_CHILD_TABLES)


def test_telegram_stays_off_and_is_rate_limited(tmp_path: Path) -> None:
    del tmp_path
    assert send_allowed((), NOW, min_interval_seconds=2, burst=1, sent_this_call=0) is True
    assert send_allowed((), NOW, min_interval_seconds=2, burst=1, sent_this_call=1) is False
    assert (
        send_allowed(
            (NOW - timedelta(seconds=1),),
            NOW,
            min_interval_seconds=30,
            burst=5,
            sent_this_call=0,
        )
        is False
    )
    off = Settings(_env_file=None, telegram_bot_token=TOKEN, telegram_chat_id="42")
    storage = MemoryStorage()
    sent: list[str] = []

    def sender(token: str, chat_id: str, text: str) -> None:
        del chat_id, text
        sent.append(token)

    result = deliver_notices(off, NOW, storage=storage, sender=sender)
    assert sent == []
    assert "Telegram delivery is off" in result.detail
    assert TOKEN not in result.detail
    assert any(item[1] == "local" and item[2] == "stored" for item in storage.records)

    enabled = Settings(
        _env_file=None,
        telegram_enabled=True,
        telegram_bot_token=TOKEN,
        telegram_chat_id="42",
        telegram_burst=1,
        telegram_min_interval_seconds=30,
    )
    limited = MemoryStorage()

    def raise_with_token(token: str, chat_id: str, text: str) -> None:
        raise OSError(f"https://api.telegram.org/bot{token}/sendMessage refused {chat_id} {text}")

    failed = deliver_notices(enabled, NOW, storage=limited, sender=raise_with_token)
    assert TOKEN not in failed.detail
    assert "42" not in failed.detail
    assert all(TOKEN not in item[3] for item in limited.records)
    assert any(item[1] == "telegram" and item[2] == "failed" for item in limited.records)

    blocked = MemoryStorage(prior=(NOW - timedelta(seconds=1),))
    calls: list[str] = []
    deferred = deliver_notices(
        enabled,
        NOW,
        storage=blocked,
        sender=lambda token, chat_id, text: calls.append(token),
    )
    assert calls == []
    assert "rate limited" in deferred.detail
    assert TOKEN not in deferred.detail


def test_notification_worker_hides_delivery_errors() -> None:
    def boom(now: datetime) -> TickResult:
        del now
        raise RuntimeError(TOKEN)

    result = NotificationWorker(database_configured=True, deliver=boom).tick(NOW)
    assert result.status == "failed"
    assert TOKEN not in result.detail
    assert "RuntimeError" in result.detail


def test_launcher_and_backup_task_are_opt_in() -> None:
    root = Path(__file__).resolve().parents[2]
    launcher = (root / "scripts" / "launch_cyvora.ps1").read_text(encoding="utf-8")
    command = (root / "scripts" / "launch_cyvora.cmd").read_text(encoding="utf-8")
    backup_task = (root / "scripts" / "register_backup_task.ps1").read_text(encoding="utf-8")
    assert "Register-ScheduledTask" not in launcher
    assert "IncludeSupervisor" in launcher
    assert "PaperTrader" in launcher
    assert "alembic upgrade head" in launcher
    assert "/health" in launcher
    assert "launch_cyvora.ps1" in command
    assert "CYVORA_BACKUP_TASK_NOT_INSTALLED" in backup_task
    assert "ConfirmInstall" in backup_task


def _settings(tmp_path: Path) -> Settings:
    del tmp_path
    return Settings(
        _env_file=None,
        log_dir=Path("logs"),
        backup_dir=Path("backups"),
        database_url=f"postgresql+psycopg://cyvora:{PASSWORD}@127.0.0.1:5432/cyvora",
    )
