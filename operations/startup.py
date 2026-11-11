"""Bounded local supervisor. The default run is one tick and does not call GMGN."""

from __future__ import annotations

import argparse
import time

from config.settings import Settings, assert_runtime_safe, get_settings
from domain.operations import RecoveryReport, RunReport
from monitoring.logging import configure_logging
from operations.assembly import default_workers
from operations.recovery import startup_recovery
from operations.supervisor import OperationsLog, Supervisor


def execute(
    settings: Settings,
    *,
    ticks: int,
    allow_radar_network: bool,
) -> tuple[RecoveryReport, RunReport]:
    """Recover the paper book, then run the workers for ``ticks`` passes."""

    recovery = startup_recovery(settings)
    log: OperationsLog | None = None
    if settings.database_url:
        from database.repositories.operations import PostgresOperationsRepository

        log = PostgresOperationsRepository(settings)
    supervisor = Supervisor(
        default_workers(settings, allow_radar_network=allow_radar_network),
        restart_limit=settings.worker_restart_limit,
        execution_mode=settings.execution_mode,
        log=log,
    )
    return recovery, supervisor.run(ticks)


def main(argv: list[str] | None = None) -> None:
    """Start a bounded run. ``--ticks 0`` repeats until interrupted."""

    parser = argparse.ArgumentParser(prog="cyvora-supervisor")
    parser.add_argument("--ticks", type=int, default=1)
    parser.add_argument("--include-radar", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=0)
    args = parser.parse_args(argv)
    if args.ticks < 0:
        print("CYVORA_SUPERVISOR_FAIL reason=ticks")
        raise SystemExit(2)
    settings = get_settings()
    assert_runtime_safe(settings)
    configure_logging(settings)
    interval = args.interval_seconds or settings.radar_scan_interval_seconds
    if args.ticks == 0 and interval < 60:
        print("CYVORA_SUPERVISOR_FAIL reason=interval")
        raise SystemExit(2)
    try:
        if args.ticks == 0:
            while True:
                _print(*execute(settings, ticks=1, allow_radar_network=args.include_radar))
                time.sleep(interval)
        else:
            _print(*execute(settings, ticks=args.ticks, allow_radar_network=args.include_radar))
    except KeyboardInterrupt:
        print("CYVORA_SUPERVISOR_STOPPED")
        raise SystemExit(0) from None


def _print(recovery: RecoveryReport, report: RunReport) -> None:
    workers = ",".join(f"{item.kind}:{item.status}" for item in report.results)
    print("CYVORA_SUPERVISOR_OK")
    print(f"ticks={report.ticks}")
    print(f"failures={report.failures}")
    print(f"critical={str(report.critical_failure).lower()}")
    print(f"workers={workers}")
    print(f"entries_blocked={str(recovery.entries_blocked).lower()}")
    print("wallet=not_authorized")
    print("live_trading_enabled=false")
    print("cloud_deployed=false")


if __name__ == "__main__":
    main()
