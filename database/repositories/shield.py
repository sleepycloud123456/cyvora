"""Load and store the Shield book in the same database as the paper ledger."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from database.models.shield import (
    ShieldCampaign,
    ShieldControl,
    ShieldDaily,
    ShieldDecision,
    ShieldEmergency,
    ShieldNoticeRow,
    ShieldStop,
)
from domain.exceptions import TradingValidationError
from domain.shield import (
    PAPER_APPROVED,
    SHIELD_DENIED,
    CampaignRecord,
    DailyBaseline,
    EmergencyFlag,
    ShieldDecisionRecord,
    ShieldNotice,
    ShieldSnapshot,
    StopPlan,
    TakeProfitSlice,
)
from shield.engine import initial_snapshot
from shield.limits import limits_from_payload, limits_payload

_DECISIONS = frozenset({PAPER_APPROVED, SHIELD_DENIED})


def read_snapshot(session: Session) -> ShieldSnapshot:
    """Return the stored book, or the documented defaults when no row exists."""

    control = session.scalar(select(ShieldControl).where(ShieldControl.id == 1))
    if control is None:
        return initial_snapshot()
    if control.live_trading_enabled:
        raise TradingValidationError("Shield rejected a stored live-trading flag.")
    daily = tuple(
        DailyBaseline(
            row.session_date,
            row.equity_at_open,
            row.last_equity,
            row.breached,
            row.recorded_at,
        )
        for row in session.scalars(select(ShieldDaily).order_by(ShieldDaily.session_date)).all()
    )
    campaigns = tuple(
        CampaignRecord(
            campaign_id=row.campaign_id,
            mint=row.mint,
            strategy_id=row.strategy_id,
            opened_at=row.opened_at,
            closed_at=row.closed_at,
            quantity_opened=row.quantity_opened,
            quantity_closed=row.quantity_closed,
            net_pnl_quote=row.net_pnl_quote,
            closing_order_id=row.closing_order_id,
            reconciliation=row.reconciliation,
            creator=row.creator,
            narrative=row.narrative,
            liquidity_provider=row.liquidity_provider,
            driver=row.driver,
            security=row.security,
        )
        for row in session.scalars(select(ShieldCampaign).order_by(ShieldCampaign.opened_at)).all()
    )
    stops = tuple(_stop(row) for row in session.scalars(select(ShieldStop)).all())
    emergencies = tuple(
        EmergencyFlag(
            row.mint,
            tuple(part for part in row.triggers.split(",") if part),
            row.recorded_at,
            row.active,
        )
        for row in session.scalars(select(ShieldEmergency)).all()
    )
    reasons = tuple(part for part in control.breach_reasons.split(",") if part)
    return ShieldSnapshot(
        limits=limits_from_payload(control.limits_json),
        high_water_equity=control.high_water_equity,
        consecutive_losses=control.consecutive_losses,
        breach_latched=control.breach_latched,
        breach_reasons=reasons,
        halt_entries=control.halt_entries,
        daily=daily,
        campaigns=campaigns,
        stops=stops,
        emergencies=emergencies,
    )


def lock_snapshot(session: Session, now: datetime) -> ShieldSnapshot:
    """Lock the singleton row, creating the documented defaults on first use."""

    control = session.scalar(select(ShieldControl).where(ShieldControl.id == 1).with_for_update())
    if control is None:
        empty = initial_snapshot()
        session.add(_control_row(empty, now))
        session.flush()
        control = session.scalar(
            select(ShieldControl).where(ShieldControl.id == 1).with_for_update()
        )
    if control is None:
        raise TradingValidationError("Shield could not lock its paper book.")
    return read_snapshot(session)


def write_snapshot(
    session: Session,
    snapshot: ShieldSnapshot,
    record: ShieldDecisionRecord | None,
    notices: tuple[ShieldNotice, ...],
    now: datetime,
) -> None:
    """Replace the book and append audit rows. Live trading is written as false."""

    if record is not None and (record.live_trading_enabled or record.decision not in _DECISIONS):
        raise TradingValidationError("Shield cannot store a live approval.")
    control = session.scalar(select(ShieldControl).where(ShieldControl.id == 1))
    payload = _control_row(snapshot, now)
    if control is None:
        session.add(payload)
    else:
        control.high_water_equity = payload.high_water_equity
        control.consecutive_losses = payload.consecutive_losses
        control.breach_latched = payload.breach_latched
        control.breach_reasons = payload.breach_reasons
        control.halt_entries = payload.halt_entries
        control.live_trading_enabled = False
        control.limits_json = payload.limits_json
        control.updated_at = now
    session.execute(delete(ShieldDaily))
    session.execute(delete(ShieldCampaign))
    session.execute(delete(ShieldStop))
    session.execute(delete(ShieldEmergency))
    session.flush()
    for daily_row in snapshot.daily:
        session.add(
            ShieldDaily(
                session_date=daily_row.session_date,
                equity_at_open=daily_row.equity_at_open,
                last_equity=daily_row.last_equity,
                breached=daily_row.breached or "daily_loss" in snapshot.breach_reasons,
                recorded_at=daily_row.recorded_at,
            )
        )
    for campaign in snapshot.campaigns:
        session.add(
            ShieldCampaign(
                campaign_id=campaign.campaign_id,
                mint=campaign.mint,
                strategy_id=campaign.strategy_id,
                opened_at=campaign.opened_at,
                closed_at=campaign.closed_at,
                quantity_opened=campaign.quantity_opened,
                quantity_closed=campaign.quantity_closed,
                net_pnl_quote=campaign.net_pnl_quote,
                closing_order_id=campaign.closing_order_id,
                reconciliation=campaign.reconciliation,
                creator=campaign.creator,
                narrative=campaign.narrative,
                liquidity_provider=campaign.liquidity_provider,
                driver=campaign.driver,
                security=campaign.security,
            )
        )
    for plan in snapshot.stops:
        session.add(
            ShieldStop(
                mint=plan.mint,
                entry_price=plan.entry_price,
                stop_price=plan.stop_price,
                peak_price=plan.peak_price,
                average_price=plan.average_price,
                quantity=plan.quantity,
                trailing_active=plan.trailing_active,
                last_trail_at=plan.last_trail_at,
                levels_json=_levels_payload(plan),
                volatility_used=plan.volatility_used,
            )
        )
    for flag in snapshot.emergencies:
        session.add(
            ShieldEmergency(
                mint=flag.mint,
                triggers=",".join(flag.triggers)[:300],
                recorded_at=flag.recorded_at,
                active=flag.active,
            )
        )
    if record is not None:
        session.add(
            ShieldDecision(
                client_order_id=record.client_order_id,
                mint=record.mint,
                side=record.side,
                decision=record.decision,
                reason=record.reason,
                requested_quantity=record.requested_quantity,
                allowed_quantity=record.allowed_quantity,
                exit_kind=record.exit_kind,
                live_trading_enabled=False,
                detail=record.detail[:300],
                recorded_at=record.recorded_at,
            )
        )
    for notice in notices:
        session.add(
            ShieldNoticeRow(
                kind=notice.kind[:32],
                detail=notice.detail[:300],
                recorded_at=notice.recorded_at,
            )
        )


def read_notices(session: Session, limit: int = 20) -> tuple[ShieldNotice, ...]:
    rows = session.scalars(
        select(ShieldNoticeRow).order_by(ShieldNoticeRow.id.desc()).limit(limit)
    ).all()
    return tuple(ShieldNotice(row.kind, row.detail, row.recorded_at) for row in reversed(rows))


def read_decisions(session: Session, limit: int = 20) -> tuple[ShieldDecisionRecord, ...]:
    rows = session.scalars(
        select(ShieldDecision).order_by(ShieldDecision.id.desc()).limit(limit)
    ).all()
    return tuple(_decision(row) for row in reversed(rows))


def mark_campaign_reconciled(session: Session, client_order_id: str) -> None:
    rows = session.scalars(
        select(ShieldCampaign).where(ShieldCampaign.closing_order_id == client_order_id)
    ).all()
    for row in rows:
        row.reconciliation = "MATCHED"


def _control_row(snapshot: ShieldSnapshot, now: datetime) -> ShieldControl:
    return ShieldControl(
        id=1,
        high_water_equity=snapshot.high_water_equity,
        consecutive_losses=snapshot.consecutive_losses,
        breach_latched=snapshot.breach_latched,
        breach_reasons=",".join(snapshot.breach_reasons)[:300],
        halt_entries=snapshot.halt_entries,
        live_trading_enabled=False,
        limits_json=limits_payload(snapshot.limits),
        updated_at=now,
    )


def _stop(row: ShieldStop) -> StopPlan:
    payload = row.levels_json if isinstance(row.levels_json, list) else []
    levels: list[TakeProfitSlice] = []
    for item in payload:
        if not isinstance(item, dict):
            raise TradingValidationError("Stored take-profit slices are unreadable.")
        levels.append(
            TakeProfitSlice(
                _money(item.get("gain"), "gain"),
                _money(item.get("fraction"), "fraction"),
                _money(item.get("planned"), "planned"),
                _money(item.get("consumed"), "consumed"),
            )
        )
    return StopPlan(
        mint=row.mint,
        entry_price=row.entry_price,
        stop_price=row.stop_price,
        peak_price=row.peak_price,
        average_price=row.average_price,
        quantity=row.quantity,
        trailing_active=row.trailing_active,
        last_trail_at=row.last_trail_at,
        levels=tuple(levels),
        volatility_used=row.volatility_used,
    )


def _levels_payload(plan: StopPlan) -> list[dict[str, str]]:
    return [
        {
            "gain": str(level.gain_fraction),
            "fraction": str(level.quantity_fraction),
            "planned": str(level.planned_quantity),
            "consumed": str(level.consumed_quantity),
        }
        for level in plan.levels
    ]


def _decision(row: ShieldDecision) -> ShieldDecisionRecord:
    return ShieldDecisionRecord(
        client_order_id=row.client_order_id,
        mint=row.mint,
        side=row.side,
        decision=row.decision,
        reason=row.reason,
        requested_quantity=row.requested_quantity,
        allowed_quantity=row.allowed_quantity,
        exit_kind=row.exit_kind,
        live_trading_enabled=False,
        detail=row.detail,
        recorded_at=row.recorded_at,
    )


def _money(value: object, label: str) -> Decimal:
    if not isinstance(value, str):
        raise TradingValidationError(f"Stored take-profit {label} is unreadable.")
    try:
        parsed = Decimal(value)
    except ArithmeticError as exc:
        raise TradingValidationError(f"Stored take-profit {label} is unreadable.") from exc
    return parsed


def utc_now() -> datetime:
    return datetime.now(UTC)
