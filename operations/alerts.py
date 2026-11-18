"""Stored facts for notices that previously had no source."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text

from config.settings import Settings
from database.connection import create_database_engine
from domain.terminal import AlertEvidence, NotificationCategory

_SECRET_MARKERS = ("password", "token", "secret", "postgresql://", "bot")


@dataclass(frozen=True, slots=True)
class ProcessEvent:
    """One lifecycle row loaded for notification drafts."""

    component: str
    action: str
    detail: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class SmartMoneySample:
    """One stored smart-wallet tag count."""

    address: str
    symbol: str | None
    cycle_id: int
    smart_wallets: int
    observed_at: datetime


def application_stopped_events(events: tuple[ProcessEvent, ...]) -> tuple[AlertEvidence, ...]:
    """Turn stopped lifecycle rows into notice evidence. Starts are ignored."""

    found: list[AlertEvidence] = []
    for event in events:
        if event.action != "stopped":
            continue
        found.append(
            AlertEvidence(
                category=NotificationCategory.APPLICATION_STOPPED.value,
                subject=event.component[:80],
                detail=_safe_stop_detail(event.component, event.detail),
                evidence_at=_aware(event.occurred_at),
            )
        )
    return tuple(found)


def accumulation_events(samples: tuple[SmartMoneySample, ...]) -> tuple[AlertEvidence, ...]:
    """Emit accumulation only when a later stored count is higher."""

    grouped: dict[str, list[SmartMoneySample]] = {}
    for sample in samples:
        grouped.setdefault(sample.address, []).append(sample)
    found: list[AlertEvidence] = []
    for address, rows in grouped.items():
        ordered = sorted(rows, key=lambda item: (item.cycle_id, item.observed_at))
        if len(ordered) < 2:
            continue
        previous, latest = ordered[-2], ordered[-1]
        if latest.smart_wallets <= previous.smart_wallets:
            continue
        label = latest.symbol or address
        found.append(
            AlertEvidence(
                category=NotificationCategory.SMART_MONEY_ACCUMULATION.value,
                subject=address[:80],
                detail=(
                    f"Stored smart-wallet tag count for {label} rose from "
                    f"{previous.smart_wallets} to {latest.smart_wallets}. "
                    "This is not an entry."
                ),
                evidence_at=_aware(latest.observed_at),
            )
        )
    return tuple(found)


def load_alert_evidence(settings: Settings) -> tuple[AlertEvidence, ...]:
    """Read lifecycle stops and smart-wallet counts. GMGN is not called."""

    if not settings.database_url:
        return ()
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            stops = connection.execute(
                text(
                    "SELECT component, action, detail, occurred_at "
                    "FROM operation_lifecycle "
                    "WHERE action = 'stopped' "
                    "ORDER BY occurred_at DESC LIMIT 20"
                )
            ).all()
            samples = connection.execute(
                text(
                    "SELECT t.address, t.symbol, e.cycle_id, e.smart_wallets, c.finished_at "
                    "FROM smart_money_events e "
                    "JOIN tokens t ON t.id = e.token_id "
                    "JOIN radar_cycles c ON c.id = e.cycle_id "
                    "WHERE e.smart_wallets IS NOT NULL "
                    "ORDER BY t.address, e.cycle_id"
                )
            ).all()
    finally:
        engine.dispose()
    events = tuple(
        ProcessEvent(str(row[0]), str(row[1]), str(row[2]), _coerce_time(row[3])) for row in stops
    )
    counts: list[SmartMoneySample] = []
    for row in samples:
        if not isinstance(row[3], int) or row[3] < 0:
            continue
        symbol = row[1] if isinstance(row[1], str) else None
        counts.append(
            SmartMoneySample(
                str(row[0]),
                symbol,
                int(row[2]),
                int(row[3]),
                _coerce_time(row[4]),
            )
        )
    return application_stopped_events(events) + accumulation_events(tuple(counts))


def _safe_stop_detail(component: str, detail: str) -> str:
    lowered = detail.lower()
    if any(marker in lowered for marker in _SECRET_MARKERS) or "://" in detail:
        return f"The {component} process stopped."
    cleaned = " ".join(detail.split())
    return cleaned[:300] or f"The {component} process stopped."


def _coerce_time(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware(value)
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
