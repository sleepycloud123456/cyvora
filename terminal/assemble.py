"""Assemble one terminal snapshot from stores that already exist."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from domain.enums import ExecutionMode
from domain.shield import ShieldDecisionRecord, ShieldNotice, ShieldSnapshot
from domain.status import StatusSnapshot
from domain.terminal import (
    NotificationPreferences,
    NotificationRecord,
    SettingsView,
    TerminalSnapshot,
    TradingProfile,
)
from domain.trading import TradingSnapshot
from intelligence.store import CycleSnapshot
from terminal.analyst import explain_stored
from terminal.analytics import build_analytics
from terminal.marks import marks_for
from terminal.notifications import build_notifications, unseen
from terminal.portfolio import build_portfolio


def assemble(
    *,
    trading: TradingSnapshot,
    shield: ShieldSnapshot,
    notices: tuple[ShieldNotice, ...],
    decisions: tuple[ShieldDecisionRecord, ...],
    cycle: CycleSnapshot | None,
    simulation_reports: tuple[Mapping[str, object], ...],
    profiles: tuple[TradingProfile, ...],
    preferences: NotificationPreferences,
    existing_notifications: tuple[NotificationRecord, ...],
    execution_mode: str,
    database_configured: bool,
    gmgn_configured: bool,
    api_host: str,
    api_port: int,
    status: StatusSnapshot | None,
    now: datetime,
) -> TerminalSnapshot:
    """Build the pages. Pending notices are the ones not already stored."""

    portfolio = build_portfolio(trading, shield, marks_for(cycle), now=now)
    analytics = build_analytics(trading.orders, shield.campaigns, shield.daily, simulation_reports)
    analyst = explain_stored(cycle=cycle, shield=shield, portfolio=portfolio, analytics=analytics)
    drafts = build_notifications(
        trading=trading,
        shield=shield,
        notices=notices,
        decisions=decisions,
        cycle=cycle,
        status=status,
        preferences=preferences,
        now=now,
    )
    pending = unseen(existing_notifications, drafts)
    active = next((item.profile_id for item in profiles if item.active), None)
    paper = execution_mode == ExecutionMode.PAPER.value
    settings = SettingsView(
        execution_mode=execution_mode,
        live_trading_enabled=False,
        live_control_present=False,
        manual_override_locked=True,
        paper_orders_allowed=paper,
        database_configured=database_configured,
        gmgn_configured=gmgn_configured,
        api_host=api_host,
        api_port=api_port,
        halt_entries=shield.halt_entries,
        breach_latched=shield.breach_latched,
        telegram_delivery=False,
    )
    return TerminalSnapshot(
        portfolio=portfolio,
        analytics=analytics,
        analyst=analyst,
        notifications=existing_notifications,
        pending_notifications=pending,
        preferences=preferences,
        profiles=profiles,
        active_profile_id=active,
        settings=settings,
        generated_at=now,
    )
