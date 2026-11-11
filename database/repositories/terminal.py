"""PostgreSQL reads and local terminal writes. No order is submitted here."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import Settings
from database.connection import create_database_engine
from database.models.terminal import TerminalNotification, TerminalPreference, TerminalProfile
from database.repositories.radar import PostgresRadarRepository
from database.repositories.simulation import PostgresSimulationRepository
from database.repositories.trading import PostgresTradingRepository
from domain.exceptions import (
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    TradingValidationError,
)
from domain.status import StatusSnapshot
from domain.terminal import (
    NotificationPreferences,
    NotificationRecord,
    TerminalSnapshot,
    TradingProfile,
)
from shield.engine import pause_entries, resume_entries
from terminal.assemble import assemble
from terminal.profiles import default_preferences, default_profile

logger = logging.getLogger("cyvora.terminal")


class PostgresTerminalRepository:
    """Load the paper book and store profiles and notices beside it."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def load(self, status: StatusSnapshot | None, now: datetime) -> TerminalSnapshot:
        self._ensure_defaults(now)
        trading_repo = PostgresTradingRepository(self._settings)
        try:
            trading = trading_repo.snapshot()
            shield = trading_repo.load_shield()
            notices = trading_repo.list_notices()
            decisions = trading_repo.list_decisions()
            cycle = PostgresRadarRepository(self._settings).latest_snapshot()
            reports = PostgresSimulationRepository(self._settings).list_runs()
            profiles = self._profiles()
            preferences = self._preferences()
            existing = self._notifications()
        except (DatabaseNotConfiguredError, DatabaseUnavailableError, TradingValidationError):
            raise
        except Exception as exc:
            logger.warning("terminal load failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Stored terminal records could not be read.") from None
        snapshot = assemble(
            trading=trading,
            shield=shield,
            notices=notices,
            decisions=decisions,
            cycle=cycle,
            simulation_reports=reports,
            profiles=profiles,
            preferences=preferences,
            existing_notifications=existing,
            execution_mode=self._settings.execution_mode.value,
            database_configured=self._settings.database_url is not None,
            gmgn_configured=self._settings.gmgn_api_key is not None,
            api_host=self._settings.api_host,
            api_port=self._settings.api_port,
            status=status,
            now=now,
        )
        self._insert(snapshot.pending_notifications, now)
        return replace(
            snapshot,
            notifications=self._notifications(),
            pending_notifications=(),
        )

    def save_profile(
        self,
        profile_id: str,
        name: str,
        strategy_ids: tuple[str, ...],
        *,
        active: bool,
        signal_threshold: str | None,
        now: datetime,
    ) -> TradingProfile:
        from terminal.profiles import normalize_profile

        profile = normalize_profile(
            profile_id,
            name,
            strategy_ids,
            active=active,
            signal_threshold=signal_threshold,
            live_trading_enabled=False,
        )
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                rows = session.scalars(select(TerminalProfile)).all()
                if not rows and not profile.active:
                    profile = replace(profile, active=True)
                if profile.active:
                    for row in rows:
                        row.active = False
                current = session.get(TerminalProfile, profile.profile_id)
                if current is None:
                    session.add(_profile_row(profile, now))
                else:
                    current.name = profile.name
                    current.strategy_ids = list(profile.strategy_ids)
                    current.signal_threshold = profile.signal_threshold
                    current.active = profile.active
                    current.live_trading_enabled = False
                    current.authority_note = profile.authority_note
                    current.updated_at = now
                session.commit()
        except (DatabaseNotConfiguredError, TradingValidationError):
            raise
        except Exception as exc:
            logger.warning("terminal profile failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The trading profile could not be stored.") from None
        finally:
            engine.dispose()
        return profile

    def activate_profile(self, profile_id: str, now: datetime) -> None:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                rows = session.scalars(select(TerminalProfile)).all()
                if not any(row.profile_id == profile_id for row in rows):
                    raise TradingValidationError("That profile is not stored.")
                for row in rows:
                    row.active = row.profile_id == profile_id
                    row.live_trading_enabled = False
                    row.updated_at = now
                session.commit()
        except (DatabaseNotConfiguredError, TradingValidationError):
            raise
        except Exception as exc:
            logger.warning("terminal activate failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The trading profile could not be selected.") from None
        finally:
            engine.dispose()

    def save_preferences(self, preferences: NotificationPreferences, now: datetime) -> None:
        if preferences.telegram_delivery or preferences.live_trading_enabled:
            raise TradingValidationError(
                "Notification settings cannot enable delivery or live trading."
            )
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                row = session.get(TerminalPreference, 1)
                if row is None:
                    session.add(_preference_row(preferences, now))
                else:
                    row.enabled_categories = list(preferences.enabled_categories)
                    row.quiet_start_minute = preferences.quiet_start_minute
                    row.quiet_end_minute = preferences.quiet_end_minute
                    row.minimum_repeat_seconds = preferences.minimum_repeat_seconds
                    row.telegram_delivery = False
                    row.live_trading_enabled = False
                    row.updated_at = now
                session.commit()
        except (DatabaseNotConfiguredError, TradingValidationError):
            raise
        except Exception as exc:
            logger.warning("terminal preferences failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Notification settings could not be stored.") from None
        finally:
            engine.dispose()

    def pause_entries(self, now: datetime) -> None:
        self._halt(now, pause=True)

    def resume_entries(self, now: datetime) -> None:
        self._halt(now, pause=False)

    def _halt(self, now: datetime, *, pause: bool) -> None:
        trading = PostgresTradingRepository(self._settings)
        snapshot = trading.load_shield()
        updated, notices = pause_entries(snapshot, now) if pause else resume_entries(snapshot, now)
        if updated is snapshot and not notices:
            return
        trading.save_shield(updated, notices=notices)

    def _ensure_defaults(self, now: datetime) -> None:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                if session.get(TerminalProfile, "paper-default") is None and not session.scalar(
                    select(TerminalProfile.profile_id).limit(1)
                ):
                    session.add(_profile_row(default_profile(), now))
                if session.get(TerminalPreference, 1) is None:
                    session.add(_preference_row(default_preferences(), now))
                session.commit()
        except DatabaseNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("terminal defaults failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Terminal defaults could not be stored.") from None
        finally:
            engine.dispose()

    def _profiles(self) -> tuple[TradingProfile, ...]:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                rows = session.scalars(
                    select(TerminalProfile).order_by(TerminalProfile.profile_id)
                ).all()
                return tuple(_profile(row) for row in rows)
        except DatabaseNotConfiguredError:
            raise
        except TradingValidationError:
            raise
        except Exception as exc:
            logger.warning("terminal profiles failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Trading profiles could not be read.") from None
        finally:
            engine.dispose()

    def _preferences(self) -> NotificationPreferences:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                row = session.get(TerminalPreference, 1)
                if row is None:
                    return default_preferences()
                return _preferences(row)
        except DatabaseNotConfiguredError:
            raise
        except TradingValidationError:
            raise
        except Exception as exc:
            logger.warning("terminal preferences read failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Notification settings could not be read.") from None
        finally:
            engine.dispose()

    def _notifications(self) -> tuple[NotificationRecord, ...]:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                rows = session.scalars(
                    select(TerminalNotification).order_by(TerminalNotification.recorded_at.desc())
                ).all()
                return tuple(_notification(row) for row in rows)
        except DatabaseNotConfiguredError:
            raise
        except TradingValidationError:
            raise
        except Exception as exc:
            logger.warning("terminal notices failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Stored notifications could not be read.") from None
        finally:
            engine.dispose()

    def _insert(self, drafts: tuple[object, ...], now: datetime) -> None:
        if not drafts:
            return
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                keys = set(session.scalars(select(TerminalNotification.dedup_key)).all())
                for draft in drafts:
                    key = getattr(draft, "dedup_key", None)
                    if not isinstance(key, str) or key in keys:
                        continue
                    session.add(
                        TerminalNotification(
                            dedup_key=key,
                            category=str(getattr(draft, "category", "")),
                            subject=str(getattr(draft, "subject", ""))[:80],
                            detail=str(getattr(draft, "detail", ""))[:480],
                            evidence_at=getattr(draft, "evidence_at", now),
                            recorded_at=now,
                            withheld=bool(getattr(draft, "withheld", False)),
                            delivered_telegram=False,
                            live_trading_enabled=False,
                        )
                    )
                    keys.add(key)
                session.commit()
        except DatabaseNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("terminal notice insert failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("A notification could not be stored.") from None
        finally:
            engine.dispose()


def _profile_row(profile: TradingProfile, now: datetime) -> TerminalProfile:
    return TerminalProfile(
        profile_id=profile.profile_id,
        name=profile.name,
        strategy_ids=list(profile.strategy_ids),
        signal_threshold=profile.signal_threshold,
        active=profile.active,
        live_trading_enabled=False,
        authority_note=profile.authority_note,
        updated_at=now,
    )


def _preference_row(preferences: NotificationPreferences, now: datetime) -> TerminalPreference:
    return TerminalPreference(
        id=1,
        enabled_categories=list(preferences.enabled_categories),
        quiet_start_minute=preferences.quiet_start_minute,
        quiet_end_minute=preferences.quiet_end_minute,
        minimum_repeat_seconds=preferences.minimum_repeat_seconds,
        telegram_delivery=False,
        live_trading_enabled=False,
        updated_at=now,
    )


def _profile(row: TerminalProfile) -> TradingProfile:
    if row.live_trading_enabled:
        raise TradingValidationError("A stored profile cannot enable live trading.")
    strategy_ids = row.strategy_ids
    identifiers = strategy_ids if isinstance(strategy_ids, list) else None
    if identifiers is None or not all(isinstance(item, str) for item in identifiers):
        raise TradingValidationError("A stored profile strategy list is invalid.")
    return TradingProfile(
        profile_id=row.profile_id,
        name=row.name,
        strategy_ids=tuple(identifiers),
        signal_threshold=row.signal_threshold,
        active=row.active,
        live_trading_enabled=False,
        authority_note=row.authority_note,
    )


def _preferences(row: TerminalPreference) -> NotificationPreferences:
    if row.telegram_delivery or row.live_trading_enabled:
        raise TradingValidationError(
            "Stored notification settings cannot enable delivery or live trading."
        )
    categories = row.enabled_categories
    if not isinstance(categories, list) or not all(isinstance(item, str) for item in categories):
        raise TradingValidationError("Stored notification categories are invalid.")
    return NotificationPreferences(
        enabled_categories=tuple(categories),
        quiet_start_minute=row.quiet_start_minute,
        quiet_end_minute=row.quiet_end_minute,
        minimum_repeat_seconds=row.minimum_repeat_seconds,
        telegram_delivery=False,
        live_trading_enabled=False,
    )


def _notification(row: TerminalNotification) -> NotificationRecord:
    if row.delivered_telegram or row.live_trading_enabled:
        raise TradingValidationError("A stored notification cannot record a live or Telegram send.")
    return NotificationRecord(
        dedup_key=row.dedup_key,
        category=row.category,
        subject=row.subject,
        detail=row.detail,
        evidence_at=row.evidence_at,
        recorded_at=row.recorded_at,
        withheld=row.withheld,
        delivered_telegram=False,
    )
