"""Authenticated local operations. These routes do not call GMGN or a signer."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from apps.api.auth import require_local_token
from apps.api.dependencies import get_app_settings
from config.settings import Settings
from domain.operations import RecoveryReport
from operations.backup import run_backup
from operations.diagnostics import export_diagnostics
from operations.recovery import startup_recovery
from operations.retention import plan_retention
from operations.startup import execute

router = APIRouter(dependencies=[Depends(require_local_token)], tags=["operations"])
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticks: int = Field(default=1, ge=1, le=3)


class BackupBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execute: bool = False


@router.get("/operations/status")
def status(request: Request, settings: SettingsDep) -> dict[str, object]:
    """Return the latest recovery and worker words. No secret is included."""

    recovery = getattr(request.app.state, "recovery", None)
    mapping = recovery.public_mapping() if isinstance(recovery, RecoveryReport) else None
    plan = plan_retention(settings)
    return {
        "live_trading_enabled": False,
        "cloud_deployed": False,
        "wallet_reconciliation": "not_authorized",
        "wallet_assumed_flat": False,
        "recovery": mapping,
        "retention": {
            "market_data_days": plan.market_data_days,
            "log_days": plan.log_days,
            "backup_files_kept": plan.backup_files_kept,
            "audit_events_deleted": plan.audit_events_deleted,
            "backtests_deleted": plan.backtests_deleted,
        },
    }


@router.post("/operations/recovery")
def recover(request: Request, settings: SettingsDep) -> dict[str, object]:
    """Read the paper book again. This does not submit an order."""

    report = startup_recovery(settings)
    request.app.state.recovery = report
    return report.public_mapping()


@router.post("/operations/supervisor/run")
def run_supervisor(body: RunBody, request: Request, settings: SettingsDep) -> dict[str, object]:
    """Run a few local ticks. The HTTP path never includes a GMGN cycle."""

    try:
        recovery, report = execute(settings, ticks=body.ticks, allow_radar_network=False)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="The supervisor tick failed.") from exc
    request.app.state.recovery = recovery
    return {
        "ticks": report.ticks,
        "failures": report.failures,
        "critical_failure": report.critical_failure,
        "live_trading_enabled": False,
        "cloud_deployed": False,
        "entries_blocked": recovery.entries_blocked,
        "workers": [
            {"kind": item.kind, "status": item.status, "detail": item.detail}
            for item in report.results
        ],
    }


@router.post("/operations/diagnostics")
def diagnostics(settings: SettingsDep, request: Request) -> dict[str, object]:
    """Write a redacted diagnostic file and return its name, not its directory."""

    recovery = getattr(request.app.state, "recovery", None)
    current = recovery if isinstance(recovery, RecoveryReport) else None
    path = export_diagnostics(settings, recovery=current, run=None)
    return {
        "file_name": path.name,
        "live_trading_enabled": False,
        "cloud_deployed": False,
    }


@router.post("/operations/backup")
def backup(body: BackupBody, settings: SettingsDep) -> dict[str, object]:
    """Plan a dump, or create one when ``execute`` is true. The URL is not returned."""

    if not body.execute:
        return {
            "status": "planned",
            "detail": "No dump was created. Send execute=true to run pg_dump locally.",
            "live_trading_enabled": False,
        }
    report = run_backup(settings)
    if settings.database_url and report.status == "completed":
        try:
            from database.repositories.operations import PostgresOperationsRepository

            PostgresOperationsRepository(settings).save_backup(report)
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="The dump was created but was not recorded."
            ) from exc
    return report.public_mapping()
