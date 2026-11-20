"""Deliver stored notices. Telegram stays off unless the environment opts in."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import Settings
from database.connection import create_database_engine
from database.models.operations import OperationDelivery
from database.models.terminal import TerminalNotification
from domain.operations import TickResult
from domain.terminal import AlertEvidence, NotificationDraft, NotificationPreferences
from monitoring.redaction import redact_text, secret_values
from operations.alerts import load_alert_evidence
from terminal.notifications import drafts_for_alerts

_LOCAL_DETAIL = "Stored for the desktop. No order was submitted."
_SENT_DETAIL = "Sent through the opt-in Telegram channel."
_FAILED_DETAIL = "Telegram delivery failed. The response was withheld."


class TelegramDeliveryError(Exception):
    """A Telegram send failed. The message is an error type, not a token or URL."""


class NoticeStorage(Protocol):
    """The rows the worker reads and writes. Implementations must not log secrets."""

    def alerts(self) -> tuple[AlertEvidence, ...]: ...

    def preferences(self) -> NotificationPreferences: ...

    def pending(self) -> tuple[PendingNotice, ...]: ...

    def prior_telegram(self, now: datetime) -> tuple[datetime, ...]: ...

    def insert_notices(self, drafts: tuple[NotificationDraft, ...], now: datetime) -> int: ...

    def record(
        self,
        dedup_key: str,
        channel: str,
        status: str,
        detail: str,
        now: datetime,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class PendingNotice:
    """A stored notice plus whether each channel already recorded it."""

    dedup_key: str
    category: str
    subject: str
    detail: str
    withheld: bool
    local_recorded: bool
    telegram_status: str | None


def telegram_ready(settings: Settings) -> bool:
    """True only when the opt-in flag, token, and numeric chat id are all set."""

    return bool(
        settings.telegram_enabled
        and settings.telegram_bot_token is not None
        and settings.telegram_chat_id
    )


def send_allowed(
    prior: tuple[datetime, ...],
    now: datetime,
    *,
    min_interval_seconds: int,
    burst: int,
    sent_this_call: int,
) -> bool:
    """Cap sends in a 60-second window and keep a gap between ticks."""

    if sent_this_call >= burst:
        return False
    recent = [item for item in prior if (now - item).total_seconds() < 60]
    if len(recent) + sent_this_call >= burst:
        return False
    too_soon = (
        sent_this_call == 0
        and bool(recent)
        and (now - max(recent)).total_seconds() < min_interval_seconds
    )
    return not too_soon


def deliver_notices(
    settings: Settings,
    now: datetime,
    *,
    storage: NoticeStorage | None = None,
    sender: Callable[[str, str, str], None] | None = None,
) -> TickResult:
    """Store new source notices and hand pending ones to the configured channels."""

    if storage is None and not settings.database_url:
        return TickResult(
            "notifications",
            "not_configured",
            "Notification storage is not configured. Telegram delivery is off.",
        )
    active = storage if storage is not None else DatabaseNoticeStorage(settings)
    moment = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    inserted = active.insert_notices(
        drafts_for_alerts(active.alerts(), preferences=active.preferences()),
        moment,
    )
    pending = active.pending()
    local = 0
    for notice in pending:
        if notice.withheld or notice.local_recorded:
            continue
        active.record(notice.dedup_key, "local", "stored", _LOCAL_DETAIL, moment)
        local += 1
    if not telegram_ready(settings):
        return _result(
            settings,
            (
                f"Local notices delivered: {local}. New notices stored: {inserted}. "
                "Telegram delivery is off."
            ),
        )
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if token is None or chat_id is None:
        return _result(
            settings,
            (
                f"Local notices delivered: {local}. New notices stored: {inserted}. "
                "Telegram delivery is off."
            ),
        )
    send = sender or post_telegram
    prior = list(active.prior_telegram(moment))
    sent = 0
    failed = 0
    deferred = 0
    secret = token.get_secret_value()
    for notice in pending:
        if notice.withheld or notice.telegram_status == "sent":
            continue
        if not send_allowed(
            tuple(prior),
            moment,
            min_interval_seconds=settings.telegram_min_interval_seconds,
            burst=settings.telegram_burst,
            sent_this_call=sent + failed,
        ):
            deferred += 1
            continue
        text = f"{notice.category}: {notice.subject}. {notice.detail} Live trading is locked."
        try:
            send(secret, chat_id, text[:500])
        except Exception as exc:
            failed += 1
            active.record(
                notice.dedup_key,
                "telegram",
                "failed",
                f"{_FAILED_DETAIL} ({type(exc).__name__})",
                moment,
            )
            continue
        sent += 1
        active.record(notice.dedup_key, "telegram", "sent", _SENT_DETAIL, moment)
    rate = ""
    if deferred:
        rate = " Telegram delivery is rate limited."
    return _result(
        settings,
        (
            f"Local notices delivered: {local}. New notices stored: {inserted}. "
            f"Telegram sent: {sent}. Telegram failed: {failed}. Telegram deferred: {deferred}."
            f"{rate}"
        ),
    )


def post_telegram(token: str, chat_id: str, text: str) -> None:
    """POST one message. Failures do not include the token or the request URL."""

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {"chat_id": chat_id, "text": text[:500], "disable_web_page_preview": True}
    ).encode()
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            code = int(response.status)
            response.read()
    except Exception as exc:
        raise TelegramDeliveryError(type(exc).__name__) from None
    if code != 200:
        raise TelegramDeliveryError("http_status")


class DatabaseNoticeStorage:
    """PostgreSQL notices and delivery rows. Connection errors omit the URL."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def alerts(self) -> tuple[AlertEvidence, ...]:
        return load_alert_evidence(self._settings)

    def preferences(self) -> NotificationPreferences:
        from database.repositories.terminal import PostgresTerminalRepository

        return PostgresTerminalRepository(self._settings).notification_preferences()

    def pending(self) -> tuple[PendingNotice, ...]:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                rows = session.scalars(select(TerminalNotification)).all()
                deliveries = session.scalars(select(OperationDelivery)).all()
        finally:
            engine.dispose()
        local = {item.dedup_key for item in deliveries if item.channel == "local"}
        telegram = {
            item.dedup_key: item.status for item in deliveries if item.channel == "telegram"
        }
        return tuple(
            PendingNotice(
                row.dedup_key,
                row.category,
                row.subject,
                row.detail,
                row.withheld,
                row.dedup_key in local,
                telegram.get(row.dedup_key),
            )
            for row in rows
        )

    def prior_telegram(self, now: datetime) -> tuple[datetime, ...]:
        cutoff = now - timedelta(seconds=60)
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                rows = session.scalars(
                    select(OperationDelivery).where(OperationDelivery.channel == "telegram")
                ).all()
        finally:
            engine.dispose()
        found: list[datetime] = []
        for row in rows:
            if row.status not in {"sent", "failed"}:
                continue
            moment = row.attempted_at
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=UTC)
            if moment >= cutoff:
                found.append(moment)
        return tuple(found)

    def insert_notices(self, drafts: tuple[NotificationDraft, ...], now: datetime) -> int:
        from database.repositories.terminal import PostgresTerminalRepository

        return PostgresTerminalRepository(self._settings).store_notices(drafts, now)

    def record(
        self,
        dedup_key: str,
        channel: str,
        status: str,
        detail: str,
        now: datetime,
    ) -> None:
        if channel not in {"local", "telegram"} or status not in {"stored", "sent", "failed"}:
            return
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                row = session.scalar(
                    select(OperationDelivery).where(
                        OperationDelivery.dedup_key == dedup_key,
                        OperationDelivery.channel == channel,
                    )
                )
                cleaned = _safe_detail(detail)
                if row is None:
                    session.add(
                        OperationDelivery(
                            dedup_key=dedup_key[:200],
                            channel=channel,
                            status=status,
                            detail=cleaned,
                            attempted_at=now,
                            live_trading_enabled=False,
                        )
                    )
                elif row.status == "sent" or (row.channel == "local" and row.status == "stored"):
                    return
                else:
                    row.status = status
                    row.detail = cleaned
                    row.attempted_at = now
                    row.live_trading_enabled = False
                session.commit()
        finally:
            engine.dispose()


def _result(settings: Settings, detail: str) -> TickResult:
    return TickResult(
        "notifications",
        "ok",
        redact_text(detail, secret_values(settings))[:300],
    )


def _safe_detail(detail: str) -> str:
    cleaned = " ".join(detail.split())
    lowered = cleaned.lower()
    if "bot" in lowered or "token" in lowered or "://" in cleaned or "password" in lowered:
        return _FAILED_DETAIL
    return cleaned[:300]
