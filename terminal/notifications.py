"""Notification drafts from stored events. No message leaves the machine."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from domain.shield import PAPER_APPROVED, ShieldNotice, ShieldSnapshot
from domain.status import StatusSnapshot
from domain.terminal import (
    CRITICAL_NOTIFICATIONS,
    NotificationCategory,
    NotificationDraft,
    NotificationPreferences,
    NotificationRecord,
)
from domain.trading import OrderRecord, OrderSide, OrderState, TradingSnapshot
from intelligence.numbers import format_decimal
from intelligence.store import CycleSnapshot

_REPEATING = frozenset(
    {
        NotificationCategory.API_DISCONNECTION,
        NotificationCategory.DATABASE_FAILURE,
        NotificationCategory.NETWORK_FAILURE,
        NotificationCategory.DAILY_LOSS,
        NotificationCategory.DRAWDOWN,
        NotificationCategory.CONSECUTIVE_LOSSES,
        NotificationCategory.EMERGENCY_STOP,
    }
)


def build_notifications(
    *,
    trading: TradingSnapshot,
    shield: ShieldSnapshot,
    notices: tuple[ShieldNotice, ...],
    decisions: tuple[object, ...],
    cycle: CycleSnapshot | None,
    status: StatusSnapshot | None,
    preferences: NotificationPreferences,
    now: datetime,
) -> tuple[NotificationDraft, ...]:
    """Create drafts for evidence that is actually stored."""

    drafts: list[NotificationDraft] = []
    drafts.extend(_cycle(cycle, now))
    drafts.extend(_orders(trading.orders))
    drafts.extend(_decisions(decisions))
    drafts.extend(_shield(shield, notices, now, preferences.minimum_repeat_seconds))
    drafts.extend(_status(status, now, preferences.minimum_repeat_seconds))
    drafts.extend(_weekly(shield, now))
    enabled = set(preferences.enabled_categories)
    kept: list[NotificationDraft] = []
    for draft in drafts:
        category = NotificationCategory(draft.category)
        if category not in enabled and category not in CRITICAL_NOTIFICATIONS:
            continue
        kept.append(_with_quiet(draft, preferences, category in CRITICAL_NOTIFICATIONS))
    return tuple(kept)


def unseen(
    existing: tuple[NotificationRecord, ...],
    drafts: tuple[NotificationDraft, ...],
) -> tuple[NotificationDraft, ...]:
    """Drop drafts whose dedup key is already stored."""

    keys = {item.dedup_key for item in existing}
    fresh: list[NotificationDraft] = []
    for draft in drafts:
        if draft.dedup_key in keys:
            continue
        keys.add(draft.dedup_key)
        fresh.append(draft)
    return tuple(fresh)


def in_quiet(moment: datetime, start: int | None, end: int | None) -> bool:
    """True when the UTC minute falls inside the quiet window."""

    if start is None or end is None or start == end:
        return False
    minute = moment.hour * 60 + moment.minute
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


def _cycle(cycle: CycleSnapshot | None, now: datetime) -> list[NotificationDraft]:
    if cycle is None or cycle.finished_at is None:
        return []
    evidence = _parse_time(cycle.finished_at, now)
    drafts: list[NotificationDraft] = []
    for discovery in cycle.discoveries:
        if discovery.source != "new_launch":
            continue
        drafts.append(
            _one(
                NotificationCategory.NEW_TOKEN,
                discovery.address,
                f"Stored new-launch row {discovery.symbol or discovery.address}.",
                evidence,
            )
        )
    for rank in cycle.rankings:
        if rank.decision == "APPROVED_FOR_FURTHER_ANALYSIS":
            drafts.append(
                _one(
                    NotificationCategory.HIGH_SCORE,
                    rank.address,
                    f"{rank.symbol or rank.address} is stored as approved for further analysis. "
                    "That is not an entry.",
                    evidence,
                )
            )
        elif rank.decision == "REJECTED":
            drafts.append(
                _one(
                    NotificationCategory.TOKEN_REJECTED,
                    rank.address,
                    f"{rank.symbol or rank.address} is stored as rejected.",
                    evidence,
                )
            )
    return drafts


def _orders(orders: tuple[OrderRecord, ...]) -> list[NotificationDraft]:
    drafts: list[NotificationDraft] = []
    for order in orders:
        if not order.simulated or order.state is not OrderState.CONFIRMED:
            continue
        if order.filled_quantity <= 0:
            continue
        if order.idempotency_key.endswith("-stop") and order.side is OrderSide.SELL:
            drafts.append(
                _one(
                    NotificationCategory.STOP_LOSS,
                    order.client_order_id,
                    f"Paper stop sell {order.symbol} was confirmed by the simulator. "
                    "A planned stop is not a guaranteed exit.",
                    order.updated_at,
                )
            )
            continue
        category = (
            NotificationCategory.SIMULATED_BUY
            if order.side is OrderSide.BUY
            else NotificationCategory.SIMULATED_SELL
        )
        drafts.append(
            _one(
                category,
                order.client_order_id,
                f"Simulator confirmed a paper {order.side.value} of {order.symbol}. "
                "This is not a chain transaction.",
                order.updated_at,
            )
        )
    return drafts


def _decisions(decisions: tuple[object, ...]) -> list[NotificationDraft]:
    drafts: list[NotificationDraft] = []
    for item in decisions:
        exit_kind = getattr(item, "exit_kind", None)
        decision = getattr(item, "decision", None)
        recorded_at = getattr(item, "recorded_at", None)
        client_order_id = getattr(item, "client_order_id", None)
        mint = getattr(item, "mint", None)
        if decision != PAPER_APPROVED or exit_kind != "take_profit":
            continue
        if not isinstance(recorded_at, datetime):
            continue
        subject = client_order_id if isinstance(client_order_id, str) else str(mint)
        drafts.append(
            _one(
                NotificationCategory.TAKE_PROFIT,
                subject,
                "Shield recorded a paper take-profit decision. The fill, if any, is simulated.",
                recorded_at,
            )
        )
    return drafts


def _shield(
    shield: ShieldSnapshot,
    notices: tuple[ShieldNotice, ...],
    now: datetime,
    repeat: int,
) -> list[NotificationDraft]:
    drafts: list[NotificationDraft] = []
    for reason in shield.breach_reasons:
        category = {
            "daily_loss": NotificationCategory.DAILY_LOSS,
            "max_drawdown": NotificationCategory.DRAWDOWN,
            "consecutive_losses": NotificationCategory.CONSECUTIVE_LOSSES,
        }.get(reason)
        if category is None:
            continue
        drafts.append(
            _repeating(
                category,
                reason,
                f"Shield breach reason {reason} is stored. Live trading stays locked.",
                now,
                repeat,
            )
        )
    if shield.consecutive_losses >= 3:
        drafts.append(
            _repeating(
                NotificationCategory.CONSECUTIVE_LOSSES,
                str(shield.consecutive_losses),
                f"Stored consecutive losing campaigns: {shield.consecutive_losses}. "
                f"The configured maximum is {shield.limits.max_consecutive_losses}.",
                now,
                repeat,
            )
        )
    for flag in shield.emergencies:
        if not flag.active:
            continue
        for trigger in flag.triggers:
            category = _trigger_category(trigger)
            if category is None:
                continue
            drafts.append(
                _one(
                    category,
                    f"{flag.mint}:{trigger}",
                    f"Shield stored {trigger} for {flag.mint}. No order was submitted.",
                    flag.recorded_at,
                )
            )
    for notice in notices:
        if notice.kind != "emergency":
            continue
        drafts.append(
            _one(
                NotificationCategory.EMERGENCY_STOP,
                notice.detail[:80],
                "Shield stored an emergency notice. It did not submit an order.",
                notice.recorded_at,
            )
        )
    return drafts


def _status(status: StatusSnapshot | None, now: datetime, repeat: int) -> list[NotificationDraft]:
    if status is None:
        return []
    drafts: list[NotificationDraft] = []
    if status.database.state == "unreachable":
        drafts.append(
            _repeating(
                NotificationCategory.DATABASE_FAILURE,
                "database",
                "PostgreSQL was configured and could not be reached.",
                now,
                repeat,
            )
        )
    if status.backend.state == "offline":
        drafts.append(
            _repeating(
                NotificationCategory.API_DISCONNECTION,
                "backend",
                "The CYVORA API is not accepting connections.",
                now,
                repeat,
            )
        )
    return drafts


def _weekly(shield: ShieldSnapshot, now: datetime) -> list[NotificationDraft]:
    if len(shield.daily) < 7:
        return []
    ordered = sorted(shield.daily, key=lambda row: row.session_date)
    first, last = ordered[0], ordered[-1]
    change = last.last_equity - first.last_equity
    shown = format_decimal(change) or "none"
    week = last.session_date.isocalendar()
    evidence = datetime(
        last.session_date.year, last.session_date.month, last.session_date.day, tzinfo=UTC
    )
    return [
        NotificationDraft(
            dedup_key=_key(
                NotificationCategory.WEEKLY_REPORT.value,
                f"{week.year}-W{week.week:02d}",
                evidence,
                repeating=False,
                repeat_seconds=3600,
            ),
            category=NotificationCategory.WEEKLY_REPORT.value,
            subject=f"{week.year}-W{week.week:02d}",
            detail=(
                f"Stored verified equity changed by {shown} from "
                f"{first.session_date.isoformat()} to {last.session_date.isoformat()}. "
                "This report is not deployed."
            ),
            evidence_at=evidence,
            withheld=False,
        )
    ]


def _trigger_category(trigger: str) -> NotificationCategory | None:
    return {
        "whale_selling": NotificationCategory.WHALE_SELLING,
        "smart_money_exit": NotificationCategory.SMART_MONEY_EXIT,
        "liquidity_removal": NotificationCategory.LIQUIDITY_REMOVAL,
        "market_data_failure": NotificationCategory.NETWORK_FAILURE,
        "trading_restriction": NotificationCategory.EMERGENCY_STOP,
        "price_collapse": NotificationCategory.EMERGENCY_STOP,
        "abnormal_impact": NotificationCategory.EMERGENCY_STOP,
    }.get(trigger)


def _with_quiet(
    draft: NotificationDraft, preferences: NotificationPreferences, critical: bool
) -> NotificationDraft:
    if critical or not in_quiet(
        draft.evidence_at, preferences.quiet_start_minute, preferences.quiet_end_minute
    ):
        return draft
    return NotificationDraft(
        draft.dedup_key,
        draft.category,
        draft.subject,
        draft.detail,
        draft.evidence_at,
        True,
    )


def _one(
    category: NotificationCategory, subject: str, detail: str, evidence: datetime
) -> NotificationDraft:
    return NotificationDraft(
        dedup_key=_key(category.value, subject, evidence, repeating=False, repeat_seconds=3600),
        category=category.value,
        subject=subject[:80],
        detail=_detail(detail),
        evidence_at=evidence,
        withheld=False,
    )


def _repeating(
    category: NotificationCategory,
    subject: str,
    detail: str,
    evidence: datetime,
    repeat_seconds: int,
) -> NotificationDraft:
    return NotificationDraft(
        dedup_key=_key(
            category.value,
            subject,
            evidence,
            repeating=category in _REPEATING,
            repeat_seconds=repeat_seconds,
        ),
        category=category.value,
        subject=subject[:80],
        detail=_detail(detail),
        evidence_at=evidence,
        withheld=False,
    )


def _key(
    category: str,
    subject: str,
    evidence: datetime,
    *,
    repeating: bool,
    repeat_seconds: int,
) -> str:
    if repeating:
        size = max(repeat_seconds, 60)
        stamp = str(int(evidence.timestamp()) // size)
    else:
        stamp = evidence.astimezone(UTC).isoformat()
    raw = f"{category}:{subject}:{stamp}"
    if len(raw) <= 180:
        return raw
    return sha256(raw.encode()).hexdigest()


def _detail(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:480]


def _parse_time(value: str, fallback: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
