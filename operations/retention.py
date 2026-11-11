"""What Phase 8 will not delete automatically."""

from __future__ import annotations

from config.settings import Settings
from domain.operations import RetentionPlan


def plan_retention(settings: Settings) -> RetentionPlan:
    """Describe retention windows. Audit rows and backtests stay stored."""

    return RetentionPlan(
        market_data_days=settings.radar_market_retention_days,
        log_days=settings.log_retention_days,
        backup_files_kept=settings.backup_files_kept,
        audit_events_deleted=False,
        backtests_deleted=False,
        notes=(
            "Audit events are not deleted.",
            "Backtesting datasets are not deleted.",
            "This plan does not remove rows.",
        ),
    )
