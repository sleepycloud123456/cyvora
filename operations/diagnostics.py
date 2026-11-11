"""Redacted diagnostic export. Environment variables are not included."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from config.settings import APP_NAME, APP_VERSION, PHASE, Settings
from domain.operations import RecoveryReport, RunReport
from monitoring.redaction import redact_text, secret_values
from readiness.guard import kill_switch_component


def build_document(
    settings: Settings,
    *,
    recovery: RecoveryReport | None,
    run: RunReport | None,
    log_text: str,
    generated_at: datetime | None = None,
) -> str:
    """Return JSON that has passed through the credential redactor."""

    moment = generated_at or datetime.now(UTC)
    payload: dict[str, object] = {
        "generated_at": moment.isoformat(),
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "phase": PHASE,
        "environment": settings.environment,
        "execution_mode": settings.execution_mode.value,
        "live_trading_enabled": False,
        "live_authorization": "not_authorized",
        "kill_switch": kill_switch_component(settings).state,
        "ready_for_live": False,
        "cloud_deployed": False,
        "wallet_reconciliation": "not_authorized",
        "wallet_assumed_flat": False,
        "recovery": None if recovery is None else recovery.public_mapping(),
        "run": None
        if run is None
        else {
            "ticks": run.ticks,
            "failures": run.failures,
            "critical_failure": run.critical_failure,
            "live_trading_enabled": False,
            "cloud_deployed": False,
            "results": [
                {"kind": item.kind, "status": item.status, "detail": item.detail}
                for item in run.results
            ],
        },
        "websocket": "not_configured",
        "queue": "in_process",
        "log_tail": log_text[-4000:],
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    return redact_text(rendered, secret_values(settings))


def read_log_tail(settings: Settings, limit: int = 80) -> str:
    """Return the last log lines, or a fixed sentence when no log exists."""

    path = settings.log_dir / "cyvora.log"
    if not path.is_file():
        return "No log file is stored."
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-limit:])


def export_diagnostics(
    settings: Settings,
    *,
    recovery: RecoveryReport | None,
    run: RunReport | None,
    now: datetime | None = None,
) -> Path:
    """Write a redacted JSON file under the diagnostics directory."""

    moment = now or datetime.now(UTC)
    document = build_document(
        settings,
        recovery=recovery,
        run=run,
        log_text=read_log_tail(settings),
        generated_at=moment,
    )
    directory = settings.diagnostics_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"cyvora-{moment.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(document, encoding="utf-8")
    return path


def main() -> None:
    """Write one redacted diagnostic file. The absolute path is not printed."""

    from config.settings import assert_runtime_safe, get_settings
    from monitoring.logging import configure_logging
    from operations.recovery import startup_recovery

    settings = get_settings()
    assert_runtime_safe(settings)
    configure_logging(settings)
    recovery = startup_recovery(settings)
    path = export_diagnostics(settings, recovery=recovery, run=None)
    print("CYVORA_DIAGNOSTICS_OK")
    print(f"file={path.name}")
    print("live_trading_enabled=false")
    print("cloud_deployed=false")


if __name__ == "__main__":
    main()
