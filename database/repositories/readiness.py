"""Store the operator kill switch and its audit. The database URL is not written."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import Settings
from database.connection import create_database_engine
from database.models.readiness import ReadinessControl, ReadinessEvent
from domain.exceptions import TradingValidationError
from domain.readiness import NOT_AUTHORIZED, KillSwitchState
from domain.readiness import ReadinessEvent as EventRecord
from readiness.kill_switch import confirmation_accepted, orders_blocked

logger = logging.getLogger("cyvora.readiness")


class ReadinessRepository:
    """Read and change the singleton latch. Live columns are always the locked values."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def engaged(self) -> bool | None:
        """Return the latch, or None when the singleton row is missing."""

        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                row = session.get(ReadinessControl, 1)
                if row is None:
                    return None
                return bool(row.kill_switch_engaged)
        finally:
            engine.dispose()

    def block_new_orders(self, now: datetime) -> bool:
        """Return true when a new operator order must be refused, and audit that refusal."""

        engaged = self.engaged()
        if not orders_blocked(engaged):
            return False
        self._audit(
            EventRecord(
                "order_refused",
                "blocked",
                "A new operator paper order was refused.",
                now,
            )
        )
        return True

    def engage(self, confirmation: str, now: datetime) -> KillSwitchState:
        if not confirmation_accepted("engage", confirmation):
            self._audit(
                EventRecord(
                    "engage_refused",
                    "refused",
                    "The kill switch engage confirmation was not accepted.",
                    now,
                )
            )
            raise TradingValidationError("The kill switch confirmation was not accepted.")
        return self._set(True, "engage", "engaged", "The kill switch was engaged.", now)

    def release(self, confirmation: str, now: datetime) -> KillSwitchState:
        if not confirmation_accepted("release", confirmation):
            self._audit(
                EventRecord(
                    "release_refused",
                    "refused",
                    "The kill switch release confirmation was not accepted.",
                    now,
                )
            )
            raise TradingValidationError("The kill switch confirmation was not accepted.")
        return self._set(False, "release", "released", "The kill switch was released.", now)

    def _set(
        self,
        engaged: bool,
        action: str,
        result: str,
        detail: str,
        now: datetime,
    ) -> KillSwitchState:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                row = session.get(ReadinessControl, 1)
                if row is None:
                    row = ReadinessControl(
                        id=1,
                        kill_switch_engaged=engaged,
                        live_trading_enabled=False,
                        authorization_state=NOT_AUTHORIZED,
                        updated_at=now,
                    )
                    session.add(row)
                else:
                    row.kill_switch_engaged = engaged
                    row.live_trading_enabled = False
                    row.authorization_state = NOT_AUTHORIZED
                    row.updated_at = now
                session.add(
                    ReadinessEvent(
                        action=action,
                        result=result,
                        detail=_clip(detail),
                        occurred_at=now,
                        live_trading_enabled=False,
                    )
                )
                session.commit()
                state = KillSwitchState(
                    engaged=bool(row.kill_switch_engaged),
                    authorization_state=NOT_AUTHORIZED,
                    updated_at=now,
                    live_trading_enabled=False,
                )
        finally:
            engine.dispose()
        return state

    def _audit(self, event: EventRecord) -> None:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                session.add(
                    ReadinessEvent(
                        action=event.action,
                        result=event.result,
                        detail=_clip(event.detail),
                        occurred_at=event.occurred_at,
                        live_trading_enabled=False,
                    )
                )
                session.commit()
        finally:
            engine.dispose()

    def recent_actions(self) -> tuple[str, ...]:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                rows = session.scalars(
                    select(ReadinessEvent.action).order_by(ReadinessEvent.id.desc()).limit(20)
                ).all()
        finally:
            engine.dispose()
        return tuple(rows)


def _clip(value: str, limit: int = 300) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
