"""Read and store local operation rows. Connection errors do not include the URL."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from config.settings import Settings
from database.connection import create_database_engine
from database.models.operations import (
    AuthEventRow,
    OperationBackup,
    OperationHeartbeat,
    OperationRecovery,
    OperationWorker,
)
from domain.exceptions import DatabaseUnavailableError
from domain.operations import (
    WALLET_NOT_AUTHORIZED,
    AuthEvent,
    BackupReport,
    BookOrder,
    BookPosition,
    BookSnapshot,
    RecoveryReport,
    TickResult,
)
from domain.status import ComponentStatus
from operations.auth_audit import open_failure_count

logger = logging.getLogger("cyvora.operations")

_HEARTBEAT_LIMIT = 20


def read_book(settings: Settings) -> BookSnapshot:
    """Load the paper book. A failed read raises and does not return zeros."""

    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            risk = connection.execute(text("SELECT id FROM shield_controls WHERE id = 1")).first()
            order_rows = connection.execute(
                text("SELECT mint, side, state, filled_quantity FROM trading_orders")
            ).all()
            position_rows = connection.execute(
                text("SELECT mint, quantity FROM trading_positions")
            ).all()
            running = connection.execute(
                text("SELECT count(*) FROM trading_strategies WHERE state = 'RUNNING'")
            ).scalar_one()
            latest = connection.execute(text("SELECT max(finished_at) FROM radar_cycles")).scalar()
    finally:
        engine.dispose()
    orders = tuple(
        BookOrder(
            mint=str(row[0]),
            side=str(row[1]),
            state=str(row[2]),
            filled_quantity=_decimal(row[3]),
        )
        for row in order_rows
    )
    positions = tuple(
        BookPosition(mint=str(row[0]), quantity=_decimal(row[1])) for row in position_rows
    )
    return BookSnapshot(
        database_state="reachable",
        risk_state="loaded" if risk is not None else "missing",
        orders=orders,
        positions=positions,
        running_strategies=int(running),
        latest_cycle_at=_aware(latest),
    )


def read_components(
    settings: Settings, now: datetime, stale_after_seconds: int
) -> tuple[ComponentStatus, ComponentStatus]:
    """Return worker and stored-cycle status words. No market data is requested."""

    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            workers = connection.execute(
                text("SELECT state, heartbeat_at FROM operation_workers")
            ).all()
            latest = connection.execute(text("SELECT max(finished_at) FROM radar_cycles")).scalar()
    finally:
        engine.dispose()
    observed = tuple((str(row[0]), _aware(row[1])) for row in workers)
    return _worker_status(observed, now, stale_after_seconds), _market_status(
        _aware(latest), now, stale_after_seconds
    )


class PostgresOperationsRepository:
    """Persist supervisor ticks and recovery reports."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def record_tick(
        self,
        result: TickResult,
        *,
        state: str,
        restarts: int,
        execution_mode: str,
        now: datetime,
    ) -> None:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                row = session.scalar(
                    select(OperationWorker).where(OperationWorker.kind == result.kind)
                )
                if row is None:
                    row = OperationWorker(
                        kind=result.kind,
                        state=state,
                        heartbeat_at=now,
                        started_at=now,
                        stopped_at=now if state in {"stopped", "failed"} else None,
                        restart_count=restarts,
                        last_error=result.detail if state == "failed" else None,
                        ticks_completed=1 if state == "stopped" else 0,
                        execution_mode=execution_mode,
                        live_trading_enabled=False,
                        cloud_deployed=False,
                        updated_at=now,
                    )
                    session.add(row)
                else:
                    row.state = state
                    row.heartbeat_at = now
                    row.stopped_at = now if state in {"stopped", "failed"} else None
                    row.restart_count = restarts
                    row.last_error = result.detail if state == "failed" else None
                    if state == "stopped":
                        row.ticks_completed += 1
                    row.execution_mode = execution_mode
                    row.live_trading_enabled = False
                    row.cloud_deployed = False
                    row.updated_at = now
                session.add(
                    OperationHeartbeat(
                        kind=result.kind,
                        observed_at=now,
                        state=state,
                        detail=_clip(f"{result.status}: {result.detail}"),
                        live_trading_enabled=False,
                    )
                )
                session.commit()
        finally:
            engine.dispose()

    def save_recovery(self, report: RecoveryReport) -> None:
        if report.wallet_reconciliation != WALLET_NOT_AUTHORIZED or report.wallet_assumed_flat:
            raise ValueError("Recovery cannot claim a wallet was read or assumed flat.")
        if report.live_trading_enabled:
            raise ValueError("Recovery cannot enable live trading.")
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                session.add(
                    OperationRecovery(
                        result=report.result,
                        database_state=report.database_state,
                        risk_state=report.risk_state,
                        pending_orders=report.pending_orders,
                        open_positions=report.open_positions,
                        unresolved_orders=report.unresolved_orders,
                        position_status=report.position_status,
                        running_strategies=report.running_strategies,
                        entries_blocked=report.entries_blocked,
                        wallet_reconciliation=report.wallet_reconciliation,
                        wallet_assumed_flat=False,
                        live_trading_enabled=False,
                        detail=_clip(report.detail, 500),
                        started_at=report.started_at,
                        finished_at=report.finished_at,
                    )
                )
                session.commit()
        finally:
            engine.dispose()

    def save_backup(self, report: BackupReport) -> None:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                session.add(
                    OperationBackup(
                        status=report.status,
                        tool=report.tool,
                        file_name=report.file_name,
                        size_bytes=report.size_bytes,
                        detail=_clip(report.detail),
                        live_trading_enabled=False,
                        started_at=report.started_at,
                        finished_at=report.finished_at,
                    )
                )
                session.commit()
        finally:
            engine.dispose()

    def save_auth(self, event: AuthEvent) -> None:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                session.add(
                    AuthEventRow(
                        result=event.result,
                        route_group=event.route_group,
                        detail=_clip(event.detail, 500),
                        occurred_at=event.occurred_at,
                        live_trading_enabled=False,
                    )
                )
                session.commit()
        finally:
            engine.dispose()

    def recent_auth_failures(self, *, now: datetime, window_seconds: float) -> int:
        """Count open authentication failures in the recent window.

        The query reads result and time only. It does not read a token.
        """

        cutoff = now - timedelta(seconds=window_seconds)
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                rows = session.execute(
                    select(AuthEventRow.result, AuthEventRow.occurred_at)
                    .where(AuthEventRow.occurred_at >= cutoff)
                    .order_by(AuthEventRow.occurred_at.desc())
                    .limit(500)
                ).all()
        except Exception as exc:
            logger.warning("auth failure read failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Authentication history could not be read.") from None
        finally:
            engine.dispose()
        events: list[tuple[str, datetime]] = []
        for row in rows:
            moment = row[1]
            if isinstance(moment, datetime):
                events.append((str(row[0]), moment))
        return open_failure_count(events, now=now, window_seconds=window_seconds)

    def recent_ticks(self) -> tuple[tuple[str, str, str], ...]:
        engine = create_database_engine(self._settings)
        try:
            with engine.connect() as connection:
                rows = connection.execute(
                    text(
                        "SELECT kind, state, detail FROM operation_heartbeats "
                        "ORDER BY id DESC LIMIT :limit"
                    ),
                    {"limit": _HEARTBEAT_LIMIT},
                ).all()
        finally:
            engine.dispose()
        return tuple((str(row[0]), str(row[1]), str(row[2])) for row in rows)


def _worker_status(
    rows: Sequence[tuple[str, datetime | None]], now: datetime, stale_after_seconds: int
) -> ComponentStatus:
    if not rows:
        return ComponentStatus(
            "not_running",
            "No supervised worker has reported a heartbeat.",
        )
    recent_failure = False
    recent = False
    for state, heartbeat in rows:
        if heartbeat is None:
            continue
        age = (now - heartbeat).total_seconds()
        if age <= stale_after_seconds:
            recent = True
            if state == "failed":
                recent_failure = True
    if recent_failure:
        return ComponentStatus(
            "degraded",
            "A supervised worker reported a failure. No order was submitted.",
        )
    if recent:
        return ComponentStatus(
            "running",
            "A supervised worker reported a recent heartbeat.",
        )
    return ComponentStatus(
        "not_running",
        "The last worker heartbeat is older than the freshness window.",
    )


def _market_status(
    latest: datetime | None, now: datetime, stale_after_seconds: int
) -> ComponentStatus:
    if latest is None:
        return ComponentStatus("missing", "No radar cycle is stored.")
    age = (now - latest).total_seconds()
    if age > stale_after_seconds:
        return ComponentStatus(
            "stale",
            "The latest stored cycle is older than the freshness window.",
        )
    return ComponentStatus(
        "fresh",
        "The latest stored cycle is inside the freshness window.",
    )


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _aware(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _clip(value: str, limit: int = 300) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
