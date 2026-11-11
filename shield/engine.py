"""Deterministic Shield decisions for paper orders.

The engine never sets live trading on. A paper approval is permission to
simulate. It is not permission to sign or submit a transaction.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from domain.exceptions import TradingValidationError
from domain.shield import (
    PAPER_APPROVED,
    SHIELD_DENIED,
    STOP_NOT_GUARANTEED,
    CampaignRecord,
    EmergencyEvidence,
    EmergencyFlag,
    Evaluation,
    ExitKind,
    RiskIntent,
    SecurityPosture,
    ShieldDecisionRecord,
    ShieldLimits,
    ShieldNotice,
    ShieldSnapshot,
    StopPlan,
)
from domain.trading import LIVE_ORDER_STATES, OrderRecord, OrderSide, PositionRecord
from shield.emergency import assess_emergency
from shield.limits import default_limits, validate_limits
from shield.numbers import quantize_down
from shield.stops import plan_take_profits, propose_stop

_TAG = re.compile(r"^[A-Za-z0-9_-]{1,48}$")
_SIGNAL = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
_SECRET_WORDS = ("private", "seed", "password", "secret", "mnemonic")
_IN_FLIGHT = frozenset(
    {
        "CREATED",
        "VALIDATED",
        "SIMULATION_PENDING",
        "SIMULATION_PASSED",
    }
)
_HALT_TRIGGERS = frozenset({"trading_restriction", "market_data_failure"})


def initial_snapshot() -> ShieldSnapshot:
    """A book with the documented defaults and no verified equity yet."""

    return ShieldSnapshot(
        limits=validate_limits(default_limits()),
        high_water_equity=None,
        consecutive_losses=0,
        breach_latched=False,
        breach_reasons=(),
        halt_entries=False,
        daily=(),
        campaigns=(),
        stops=(),
        emergencies=(),
    )


def evaluate(
    snapshot: ShieldSnapshot,
    intent: RiskIntent,
    positions: tuple[PositionRecord, ...],
    orders: tuple[OrderRecord, ...],
    now: datetime,
) -> Evaluation:
    """Decide one paper intent. The returned snapshot includes verified observations."""

    _require_clock(now)
    limits = validate_limits(snapshot.limits)
    side = _side(intent.side)
    if side is OrderSide.BUY:
        return _evaluate_buy(snapshot, limits, intent, positions, orders, now)
    return _evaluate_sell(snapshot, limits, intent, positions, orders, now)


def apply_execution(
    snapshot: ShieldSnapshot,
    *,
    order: OrderRecord,
    position_before: PositionRecord | None,
    position_after: PositionRecord | None,
    intent: RiskIntent,
    effective_stop: Decimal | None,
    exit_kind: str,
    now: datetime,
) -> tuple[ShieldSnapshot, tuple[ShieldNotice, ...]]:
    """Update campaigns and stops after a fill. A zero fill changes neither."""

    if order.filled_quantity <= 0 or position_after is None:
        return snapshot, ()
    if order.side is OrderSide.BUY:
        opened = _open_campaign_record(snapshot, order, position_after, intent, effective_stop, now)
        return opened, ()
    return _close_quantity(
        snapshot,
        order,
        position_before,
        position_after,
        exit_kind,
        intent,
        now,
    )


def mark_reconciled(snapshot: ShieldSnapshot, client_order_id: str) -> ShieldSnapshot:
    """Record a matched reconciliation so a later re-entry can be considered."""

    campaigns: list[CampaignRecord] = []
    for campaign in snapshot.campaigns:
        if campaign.closing_order_id == client_order_id:
            campaigns.append(replace(campaign, reconciliation="MATCHED"))
        else:
            campaigns.append(campaign)
    return replace(snapshot, campaigns=tuple(campaigns))


def recover(
    snapshot: ShieldSnapshot,
    phrase: str,
    intent: RiskIntent,
    positions: tuple[PositionRecord, ...],
    now: datetime,
    *,
    reset_loss_streak: bool,
) -> tuple[ShieldSnapshot, str | None, tuple[ShieldNotice, ...]]:
    """Clear a latched breach only when the current figures are back inside the limits."""

    from domain.shield import RECOVERY_PHRASE

    if phrase != RECOVERY_PHRASE:
        return snapshot, "recovery_phrase", ()
    observed, equity, problem = _observe(snapshot, intent, positions, now)
    if problem is not None or equity is None:
        return observed, problem or "valuation_unverified", ()
    reasons: list[str] = list(observed.breach_reasons)
    if _daily_breached(observed, equity, observed.limits) and "daily_loss" not in reasons:
        reasons.append("daily_loss")
    if _drawdown_breached(observed, equity, observed.limits) and "max_drawdown" not in reasons:
        reasons.append("max_drawdown")
    still: list[str] = [
        reason
        for reason in ("daily_loss", "max_drawdown")
        if reason in reasons and _reason_still(reason, observed, equity)
    ]
    if (
        observed.consecutive_losses >= observed.limits.max_consecutive_losses
        and not reset_loss_streak
    ):
        still.append("consecutive_losses")
    if observed.halt_entries:
        triggers = _recovery_triggers(intent, observed.limits, now)
        if triggers is None or _HALT_TRIGGERS.intersection(triggers):
            still.append("entries_halted")
    if still:
        refused = replace(
            observed,
            breach_latched=True,
            breach_reasons=tuple(sorted(set(reasons))),
        )
        return refused, "recovery_refused", ()
    streak = 0 if reset_loss_streak else observed.consecutive_losses
    cleared = replace(
        observed,
        consecutive_losses=streak,
        breach_latched=False,
        breach_reasons=(),
        halt_entries=False,
    )
    notice = ShieldNotice("recovery", "Paper entries can be evaluated again.", now)
    return cleared, None, (notice,)


def replace_limits(snapshot: ShieldSnapshot, limits: ShieldLimits) -> ShieldSnapshot:
    """Store a new configuration. This does not clear a breach or the high-water mark."""

    return replace(snapshot, limits=validate_limits(limits))


def record_emergency(
    snapshot: ShieldSnapshot,
    mint: str,
    evidence: EmergencyEvidence | None,
    now: datetime,
) -> tuple[ShieldSnapshot, tuple[str, ...], tuple[ShieldNotice, ...]]:
    """Store triggers for a mint. No order is created."""

    triggers = assess_emergency(evidence, snapshot.limits, now)
    if not triggers:
        return snapshot, (), ()
    flags = [flag for flag in snapshot.emergencies if flag.mint != mint]
    flags.append(EmergencyFlag(mint, triggers, now, True))
    halt = snapshot.halt_entries or bool(_HALT_TRIGGERS.intersection(triggers))
    updated = replace(snapshot, emergencies=tuple(flags), halt_entries=halt)
    notice = ShieldNotice("emergency", f"{mint}:" + ",".join(triggers), now)
    return updated, triggers, (notice,)


def record_trail(
    snapshot: ShieldSnapshot,
    mint: str,
    mark: Decimal,
    volatility: Decimal | None,
    now: datetime,
) -> tuple[ShieldSnapshot, str]:
    """Advance one stored stop. Missing volatility is not replaced with a guess."""

    from shield.stops import advance_trailing

    plan = next((item for item in snapshot.stops if item.mint == mint), None)
    if plan is None:
        raise TradingValidationError("That mint has no stored stop plan.")
    if mark <= 0:
        raise TradingValidationError("A trailing mark must be positive.")
    if volatility is not None and volatility <= 0:
        raise TradingValidationError("Volatility must be positive when it is supplied.")
    updated, status = advance_trailing(plan, mark, now, volatility, snapshot.limits)
    stops = tuple(updated if item.mint == mint else item for item in snapshot.stops)
    return replace(snapshot, stops=stops), status


def decision_record(
    evaluation: Evaluation,
    *,
    client_order_id: str | None,
    intent: RiskIntent,
    now: datetime,
) -> ShieldDecisionRecord:
    """Build the audit row. Live trading stays false for both outcomes."""

    detail = "; ".join(evaluation.notes)[:300]
    return ShieldDecisionRecord(
        client_order_id=client_order_id,
        mint=intent.mint,
        side=intent.side,
        decision=PAPER_APPROVED if evaluation.approved else SHIELD_DENIED,
        reason=evaluation.reason,
        requested_quantity=intent.quantity,
        allowed_quantity=evaluation.allowed_quantity,
        exit_kind=evaluation.exit_kind,
        live_trading_enabled=False,
        detail=detail,
        recorded_at=now,
    )


def _evaluate_buy(
    snapshot: ShieldSnapshot,
    limits: ShieldLimits,
    intent: RiskIntent,
    positions: tuple[PositionRecord, ...],
    orders: tuple[OrderRecord, ...],
    now: datetime,
) -> Evaluation:
    if intent.exit_kind != ExitKind.ENTRY.value:
        return _deny(snapshot, intent, "exit_kind_invalid", now)
    if intent.quote_symbol != "SOL":
        return _deny(snapshot, intent, "quote_not_sol", now)
    _tags(intent)
    observed, equity, problem = _observe(snapshot, intent, positions, now)
    if problem is not None or equity is None:
        return _deny(snapshot, intent, problem or "valuation_unverified", now)
    security = _security(intent.security)
    if security is SecurityPosture.UNKNOWN:
        return _deny(observed, intent, "security_unknown", now)
    if security is SecurityPosture.RESTRICTED:
        return _deny(observed, intent, "security_restricted", now)
    if observed.halt_entries or _active_emergency(observed, intent.mint):
        return _deny(observed, intent, "emergency_stop", now, notices=_halt_notice(observed, now))
    if (
        observed.breach_latched
        or _daily_breached(observed, equity, limits)
        or _drawdown_breached(observed, equity, limits)
    ):
        latched, notices = _latch(observed, equity, limits, now)
        return _deny(latched, intent, _breach_reason(latched, equity, limits), now, notices=notices)
    if observed.consecutive_losses >= limits.max_consecutive_losses:
        latched, notices = _latch(observed, equity, limits, now)
        return _deny(latched, intent, "consecutive_losses", now, notices=notices)
    campaign_reason = _entry_block(observed, intent.mint)
    if campaign_reason is not None:
        return _deny(observed, intent, campaign_reason, now)
    emergency_reason = _entry_emergency(observed, intent, limits, now)
    if emergency_reason is not None:
        return _deny(
            emergency_reason[0], intent, "emergency_stop", now, notices=emergency_reason[1]
        )
    sized = _size_buy(observed, limits, intent, positions, orders, equity)
    if sized.reason is not None:
        return _deny(
            observed,
            intent,
            sized.reason,
            now,
            allowed=sized.allowed,
            binding=sized.binding,
            notes=sized.notes,
            stop=sized.stop,
            fill=sized.fill,
        )
    notes = sized.notes + (STOP_NOT_GUARANTEED,)
    return Evaluation(
        observed,
        True,
        None,
        intent.quantity,
        None,
        notes,
        sized.stop,
        sized.fill,
        ExitKind.ENTRY.value,
        (),
    )


def _evaluate_sell(
    snapshot: ShieldSnapshot,
    limits: ShieldLimits,
    intent: RiskIntent,
    positions: tuple[PositionRecord, ...],
    orders: tuple[OrderRecord, ...],
    now: datetime,
) -> Evaluation:
    del orders
    position = next((item for item in positions if item.mint == intent.mint), None)
    available = Decimal(0) if position is None else position.quantity
    if intent.quantity > available:
        return _deny(snapshot, intent, "insufficient_position", now)
    kind = _exit_kind(intent.exit_kind)
    if kind is ExitKind.ENTRY:
        return _deny(snapshot, intent, "exit_kind_invalid", now)
    if kind is ExitKind.SIGNAL and (
        intent.signal_ref is None or _SIGNAL.fullmatch(intent.signal_ref) is None
    ):
        return _deny(snapshot, intent, "signal_missing", now)
    if kind is ExitKind.TIME:
        reason = _time_ready(snapshot, intent.mint, limits, now)
        if reason is not None:
            return _deny(snapshot, intent, reason, now)
    if kind is ExitKind.EMERGENCY:
        triggers = assess_emergency(intent.emergency, limits, now)
        flagged = _active_emergency(snapshot, intent.mint)
        if not triggers and not flagged:
            return _deny(snapshot, intent, "emergency_evidence_missing", now)
    if kind is ExitKind.TAKE_PROFIT:
        reason = _take_profit_ready(snapshot, intent, now)
        if reason is not None:
            return _deny(snapshot, intent, reason, now)
    observed = snapshot
    if intent.equity_quote is not None:
        observed, _equity, problem = _observe(snapshot, intent, positions, now)
        if problem is not None:
            observed = snapshot
    return Evaluation(
        observed,
        True,
        None,
        intent.quantity,
        None,
        ("Reduce-only paper exit. Live execution stays disabled.",),
        None,
        None,
        kind.value,
        (),
    )


class _Size:
    def __init__(
        self,
        *,
        reason: str | None,
        allowed: Decimal | None,
        binding: str | None,
        notes: tuple[str, ...],
        stop: Decimal | None,
        fill: Decimal | None,
    ) -> None:
        self.reason = reason
        self.allowed = allowed
        self.binding = binding
        self.notes = notes
        self.stop = stop
        self.fill = fill


def _size_buy(
    snapshot: ShieldSnapshot,
    limits: ShieldLimits,
    intent: RiskIntent,
    positions: tuple[PositionRecord, ...],
    orders: tuple[OrderRecord, ...],
    equity: Decimal,
) -> _Size:
    if intent.market_condition not in {None, "calm", "stressed"}:
        raise TradingValidationError("Market condition must be calm, stressed, or omitted.")
    if intent.token_age_seconds is not None and intent.token_age_seconds < 0:
        raise TradingValidationError("Token age cannot be negative.")
    fill = intent.reference_price + intent.slippage_quote
    if fill <= 0:
        return _Size(
            reason="stop_not_below_entry",
            allowed=None,
            binding="stop",
            notes=(),
            stop=None,
            fill=fill,
        )
    notes: list[str] = []
    explicit = intent.stop_price
    volatility_stop: Decimal | None = None
    if intent.volatility is not None:
        if intent.volatility <= 0:
            raise TradingValidationError("Volatility must be positive when it is supplied.")
        volatility_stop, stop_notes = propose_stop(
            fill,
            intent.volatility,
            equity=equity,
            liquidity_quote=intent.liquidity_quote,
            token_age_seconds=intent.token_age_seconds,
            market_condition=intent.market_condition,
            slippage_quote=intent.slippage_quote,
            limits=limits,
        )
        notes.extend(stop_notes)
    else:
        notes.append("volatility_not_supplied")
    candidates = [price for price in (explicit, volatility_stop) if price is not None]
    if not candidates:
        return _Size(
            reason="stop_unverified",
            allowed=None,
            binding="stop",
            notes=tuple(notes),
            stop=None,
            fill=fill,
        )
    stop = min(candidates)
    if stop <= 0 or stop >= fill:
        return _Size(
            reason="stop_not_below_entry",
            allowed=Decimal(0),
            binding="stop",
            notes=tuple(notes),
            stop=stop,
            fill=fill,
        )
    if intent.confidence is not None and (intent.confidence <= 0 or intent.confidence > 1):
        raise TradingValidationError("Strategy confidence must be greater than 0 and at most 1.")
    budget = equity * limits.risk_per_trade_fraction
    if intent.confidence is not None:
        budget *= intent.confidence
    else:
        notes.append("confidence_not_supplied")
    fee_per_unit = intent.fee_quote / intent.quantity
    loss_per_unit = (fill - stop) + fee_per_unit
    unit_cost = fill + fee_per_unit
    caps: list[tuple[str, Decimal]] = [("risk_per_trade", budget / loss_per_unit)]
    marked = _deployed(positions, intent.marks)
    if marked is None:
        return _Size(
            reason="valuation_unverified",
            allowed=None,
            binding="valuation",
            notes=tuple(notes),
            stop=stop,
            fill=fill,
        )
    deployed = marked + _pending_notional(orders)
    deployed_room = equity * limits.max_deployed_fraction - deployed
    caps.append(("max_deployed", deployed_room / fill if fill > 0 else Decimal(0)))
    reserve = equity * limits.min_sol_reserve_fraction
    sol_balance = intent.sol_balance if intent.sol_balance is not None else Decimal(0)
    spendable = sol_balance - reserve
    caps.append(("sol_reserve", spendable / unit_cost if unit_cost > 0 else Decimal(0)))
    if intent.liquidity_quote is None or intent.liquidity_quote <= 0:
        return _Size(
            reason="liquidity_unverified",
            allowed=None,
            binding="liquidity",
            notes=tuple(notes),
            stop=stop,
            fill=fill,
        )
    liquidity_room = intent.liquidity_quote * limits.max_liquidity_participation
    caps.append(("liquidity_participation", liquidity_room / fill))
    if intent.estimated_impact is not None:
        if intent.estimated_impact < 0:
            raise TradingValidationError("Price impact cannot be negative.")
        if intent.estimated_impact > limits.max_price_impact:
            caps.append(("price_impact", Decimal(0)))
    else:
        notes.append("price_impact_not_supplied")
    cluster = _cluster_room(snapshot, intent, positions, equity, limits)
    if cluster.reason is not None:
        return _Size(
            reason=cluster.reason,
            allowed=cluster.allowed,
            binding="correlation",
            notes=tuple(notes),
            stop=stop,
            fill=fill,
        )
    if cluster.allowed is not None:
        caps.append(("correlation_cluster", cluster.allowed))
    binding, raw_allowed = min(caps, key=lambda item: item[1])
    allowed = quantize_down(raw_allowed, intent.size_decimals)
    if allowed < 0:
        allowed = Decimal(0)
    if intent.quantity > allowed:
        return _Size(
            reason=binding,
            allowed=allowed,
            binding=binding,
            notes=tuple(notes) + (STOP_NOT_GUARANTEED,),
            stop=stop,
            fill=fill,
        )
    return _Size(
        reason=None, allowed=intent.quantity, binding=None, notes=tuple(notes), stop=stop, fill=fill
    )


class _Cluster:
    def __init__(self, reason: str | None, allowed: Decimal | None) -> None:
        self.reason = reason
        self.allowed = allowed


def _cluster_room(
    snapshot: ShieldSnapshot,
    intent: RiskIntent,
    positions: tuple[PositionRecord, ...],
    equity: Decimal,
    limits: ShieldLimits,
) -> _Cluster:
    open_positions = [
        position for position in positions if position.quantity > 0 and position.mint != intent.mint
    ]
    if not open_positions:
        return _Cluster(None, None)
    incoming = _evidence_tags(intent)
    if incoming is None:
        return _Cluster("correlation_unknown", None)
    exposure = Decimal(0)
    marks = dict(intent.marks)
    for position in open_positions:
        campaign = _find_open_campaign(snapshot, position.mint)
        if campaign is None or _campaign_tags(campaign) is None:
            return _Cluster("correlation_unknown", None)
        if _shares(incoming, _campaign_tags(campaign) or ()):
            mark = marks.get(position.mint)
            if mark is None:
                return _Cluster("valuation_unverified", None)
            exposure += position.quantity * mark
    room = equity * limits.max_cluster_fraction - exposure
    fill = intent.reference_price + intent.slippage_quote
    if fill <= 0:
        return _Cluster("correlation_cluster", Decimal(0))
    return _Cluster(None, room / fill)


def _observe(
    snapshot: ShieldSnapshot,
    intent: RiskIntent,
    positions: tuple[PositionRecord, ...],
    now: datetime,
) -> tuple[ShieldSnapshot, Decimal | None, str | None]:
    equity = intent.equity_quote
    sol_balance = intent.sol_balance
    valued_at = intent.valued_at
    if equity is None or sol_balance is None or valued_at is None:
        return snapshot, None, "valuation_unverified"
    _require_clock(valued_at)
    if equity <= 0 or sol_balance < 0:
        raise TradingValidationError(
            "Verified equity must be positive and SOL balance cannot be negative."
        )
    if valued_at - now > timedelta(seconds=5) or now - valued_at > timedelta(
        seconds=snapshot.limits.max_valuation_age_seconds
    ):
        return snapshot, None, "valuation_stale"
    marked = _deployed(positions, intent.marks)
    if marked is None:
        return snapshot, None, "valuation_unverified"
    if equity != sol_balance + marked:
        return snapshot, None, "valuation_inconsistent"
    session = now.astimezone(UTC).date()
    daily = list(snapshot.daily)
    current = next((row for row in daily if row.session_date == session), None)
    if current is None:
        from domain.shield import DailyBaseline

        current = DailyBaseline(session, equity, equity, False, now)
        daily.append(current)
    else:
        daily = [
            replace(row, last_equity=equity, recorded_at=now)
            if row.session_date == session
            else row
            for row in daily
        ]
        current = next(row for row in daily if row.session_date == session)
    high = equity if snapshot.high_water_equity is None else max(snapshot.high_water_equity, equity)
    updated = replace(snapshot, high_water_equity=high, daily=tuple(daily))
    breached = _daily_breached(updated, equity, updated.limits) or _drawdown_breached(
        updated, equity, updated.limits
    )
    if breached or updated.consecutive_losses >= updated.limits.max_consecutive_losses:
        updated, _notices = _latch(updated, equity, updated.limits, now)
    return updated, equity, None


def _latch(
    snapshot: ShieldSnapshot,
    equity: Decimal,
    limits: ShieldLimits,
    now: datetime,
) -> tuple[ShieldSnapshot, tuple[ShieldNotice, ...]]:
    reasons = set(snapshot.breach_reasons)
    if _daily_breached(snapshot, equity, limits):
        reasons.add("daily_loss")
    if _drawdown_breached(snapshot, equity, limits):
        reasons.add("max_drawdown")
    if snapshot.consecutive_losses >= limits.max_consecutive_losses:
        reasons.add("consecutive_losses")
    ordered = tuple(sorted(reasons))
    if snapshot.breach_latched and ordered == snapshot.breach_reasons:
        return snapshot, ()
    updated = replace(snapshot, breach_latched=True, breach_reasons=ordered)
    detail = ",".join(ordered) if ordered else "breach"
    return updated, (ShieldNotice("breach", detail, now),)


def _daily_breached(snapshot: ShieldSnapshot, equity: Decimal, limits: ShieldLimits) -> bool:
    if not snapshot.daily:
        return False
    current = max(snapshot.daily, key=lambda row: row.session_date)
    if current.equity_at_open <= 0 or equity >= current.equity_at_open:
        return False
    loss = (current.equity_at_open - equity) / current.equity_at_open
    return loss >= limits.daily_loss_fraction


def _drawdown_breached(snapshot: ShieldSnapshot, equity: Decimal, limits: ShieldLimits) -> bool:
    high = snapshot.high_water_equity
    if high is None or high <= 0 or equity >= high:
        return False
    return (high - equity) / high >= limits.max_drawdown_fraction


def _reason_still(reason: str, snapshot: ShieldSnapshot, equity: Decimal) -> bool:
    if reason == "daily_loss":
        return _daily_breached(snapshot, equity, snapshot.limits)
    if reason == "max_drawdown":
        return _drawdown_breached(snapshot, equity, snapshot.limits)
    return False


def _breach_reason(snapshot: ShieldSnapshot, equity: Decimal, limits: ShieldLimits) -> str:
    if _daily_breached(snapshot, equity, limits):
        return "daily_loss"
    if _drawdown_breached(snapshot, equity, limits):
        return "max_drawdown"
    if snapshot.breach_reasons:
        return snapshot.breach_reasons[0]
    return "daily_loss"


def _deployed(
    positions: tuple[PositionRecord, ...], marks: tuple[tuple[str, Decimal], ...]
) -> Decimal | None:
    table = dict(marks)
    total = Decimal(0)
    for position in positions:
        if position.quantity <= 0:
            continue
        mark = table.get(position.mint)
        if mark is None or mark <= 0:
            return None
        total += position.quantity * mark
    return total


def _pending_notional(orders: tuple[OrderRecord, ...]) -> Decimal:
    total = Decimal(0)
    for order in orders:
        if order.side is not OrderSide.BUY or order.state.value not in _IN_FLIGHT:
            continue
        if order.state in LIVE_ORDER_STATES:
            continue
        remaining = order.quantity - order.filled_quantity
        if remaining > 0:
            total += remaining * order.reference_price
    return total


def _entry_block(snapshot: ShieldSnapshot, mint: str) -> str | None:
    if _find_open_campaign(snapshot, mint) is not None:
        return "position_already_open"
    closed = [
        item for item in snapshot.campaigns if item.mint == mint and item.closed_at is not None
    ]
    if not closed:
        return None
    latest = max(closed, key=lambda item: item.closed_at or item.opened_at)
    if latest.reconciliation != "MATCHED":
        return "reentry_not_reconciled"
    return None


def _entry_emergency(
    snapshot: ShieldSnapshot,
    intent: RiskIntent,
    limits: ShieldLimits,
    now: datetime,
) -> tuple[ShieldSnapshot, tuple[ShieldNotice, ...]] | None:
    if intent.emergency is None and not _active_emergency(snapshot, intent.mint):
        return None
    triggers = (
        assess_emergency(intent.emergency, limits, now) if intent.emergency is not None else ()
    )
    if not triggers and not _active_emergency(snapshot, intent.mint):
        return None
    if not triggers:
        return snapshot, ()
    updated, _stored, notices = record_emergency(snapshot, intent.mint, intent.emergency, now)
    return updated, notices


def _find_open_campaign(snapshot: ShieldSnapshot, mint: str) -> CampaignRecord | None:
    return next(
        (item for item in snapshot.campaigns if item.mint == mint and item.closed_at is None),
        None,
    )


def _open_campaign_record(
    snapshot: ShieldSnapshot,
    order: OrderRecord,
    position: PositionRecord,
    intent: RiskIntent,
    effective_stop: Decimal | None,
    now: datetime,
) -> ShieldSnapshot:
    if effective_stop is None:
        return snapshot
    campaign = CampaignRecord(
        campaign_id=order.client_order_id,
        mint=order.mint,
        strategy_id=order.strategy_id,
        opened_at=now,
        closed_at=None,
        quantity_opened=order.filled_quantity,
        quantity_closed=Decimal(0),
        net_pnl_quote=Decimal(0),
        closing_order_id=None,
        reconciliation=None,
        creator=_clean_tag(intent.creator),
        narrative=_clean_tag(intent.narrative),
        liquidity_provider=_clean_tag(intent.liquidity_provider),
        driver=_clean_tag(intent.driver),
        security=SecurityPosture.CLEAR.value,
    )
    average = position.average_price if position.average_price is not None else order.fill_price
    if average is None:
        return snapshot
    plan = StopPlan(
        mint=order.mint,
        entry_price=order.fill_price or intent.reference_price,
        stop_price=effective_stop,
        peak_price=order.fill_price or intent.reference_price,
        average_price=average,
        quantity=position.quantity,
        trailing_active=False,
        last_trail_at=None,
        levels=plan_take_profits(position.quantity, snapshot.limits, intent.size_decimals),
        volatility_used=intent.volatility is not None,
    )
    stops = tuple(item for item in snapshot.stops if item.mint != order.mint)
    return replace(
        snapshot,
        campaigns=snapshot.campaigns + (campaign,),
        stops=stops + (plan,),
    )


def _close_quantity(
    snapshot: ShieldSnapshot,
    order: OrderRecord,
    position_before: PositionRecord | None,
    position_after: PositionRecord,
    exit_kind: str,
    intent: RiskIntent,
    now: datetime,
) -> tuple[ShieldSnapshot, tuple[ShieldNotice, ...]]:
    campaign = _find_open_campaign(snapshot, order.mint)
    if campaign is None or position_before is None:
        return snapshot, ()
    before = position_before.realized_pnl_quote
    delta = position_after.realized_pnl_quote - before
    closed_qty = campaign.quantity_closed + order.filled_quantity
    net = campaign.net_pnl_quote + delta
    flat = position_after.quantity == 0
    updated_campaign = replace(
        campaign,
        quantity_closed=closed_qty,
        net_pnl_quote=net,
        closed_at=now if flat else None,
        closing_order_id=order.client_order_id if flat else campaign.closing_order_id,
    )
    campaigns = tuple(
        updated_campaign if item.campaign_id == campaign.campaign_id else item
        for item in snapshot.campaigns
    )
    stops = snapshot.stops
    notices: tuple[ShieldNotice, ...] = ()
    streak = snapshot.consecutive_losses
    latched = snapshot.breach_latched
    reasons = snapshot.breach_reasons
    if flat:
        stops = tuple(item for item in stops if item.mint != order.mint)
        if net < 0:
            streak += 1
        elif net > 0:
            streak = 0
        if streak >= snapshot.limits.max_consecutive_losses:
            reasons = tuple(sorted(set(reasons) | {"consecutive_losses"}))
            if not latched or "consecutive_losses" not in snapshot.breach_reasons:
                notices = (ShieldNotice("breach", "consecutive_losses", now),)
            latched = True
    else:
        mark = dict(intent.marks).get(order.mint)
        stops = tuple(
            _reduce_stop(item, position_after.quantity, order.filled_quantity, exit_kind, mark)
            if item.mint == order.mint
            else item
            for item in stops
        )
    return (
        replace(
            snapshot,
            campaigns=campaigns,
            stops=stops,
            consecutive_losses=streak,
            breach_latched=latched,
            breach_reasons=reasons,
        ),
        notices,
    )


def _reduce_stop(
    plan: StopPlan,
    quantity: Decimal,
    sold: Decimal,
    exit_kind: str,
    mark: Decimal | None,
) -> StopPlan:
    updated = plan
    if exit_kind == ExitKind.TAKE_PROFIT.value and mark is not None:
        updated = _consume_level(updated, sold, mark)
    return _fit_levels(updated, quantity)


def _consume_level(plan: StopPlan, sold: Decimal, mark: Decimal) -> StopPlan:
    levels = []
    taken = False
    for level in plan.levels:
        target = plan.entry_price * (Decimal(1) + level.gain_fraction)
        left = level.planned_quantity - level.consumed_quantity
        if not taken and mark >= target and left > 0:
            levels.append(replace(level, consumed_quantity=level.consumed_quantity + sold))
            taken = True
        else:
            levels.append(level)
    return replace(plan, levels=tuple(levels))


def _fit_levels(plan: StopPlan, quantity: Decimal) -> StopPlan:
    unconsumed = sum(
        (level.planned_quantity - level.consumed_quantity for level in plan.levels),
        Decimal(0),
    )
    overflow = unconsumed - quantity
    if overflow <= 0:
        return replace(plan, quantity=quantity)
    levels = list(plan.levels)
    for index in range(len(levels) - 1, -1, -1):
        level = levels[index]
        left = level.planned_quantity - level.consumed_quantity
        if left <= 0:
            continue
        cut = left if left < overflow else overflow
        levels[index] = replace(level, planned_quantity=level.planned_quantity - cut)
        overflow -= cut
        if overflow <= 0:
            break
    return replace(plan, levels=tuple(levels), quantity=quantity)


def _take_profit_ready(snapshot: ShieldSnapshot, intent: RiskIntent, now: datetime) -> str | None:
    del now
    plan = next((item for item in snapshot.stops if item.mint == intent.mint), None)
    if plan is None:
        return "take_profit_not_reached"
    mark = dict(intent.marks).get(intent.mint)
    if mark is None:
        return "valuation_unverified"
    remaining = None
    for level in plan.levels:
        target = plan.entry_price * (Decimal(1) + level.gain_fraction)
        left = level.planned_quantity - level.consumed_quantity
        if mark >= target and left > 0:
            remaining = left
            break
    if remaining is None:
        return "take_profit_not_reached"
    if intent.quantity > remaining:
        return "take_profit_quantity"
    return None


def _time_ready(
    snapshot: ShieldSnapshot, mint: str, limits: ShieldLimits, now: datetime
) -> str | None:
    campaign = _find_open_campaign(snapshot, mint)
    if campaign is None:
        return "time_exit_not_due"
    if now - campaign.opened_at < timedelta(seconds=limits.time_exit_seconds):
        return "time_exit_not_due"
    return None


def _active_emergency(snapshot: ShieldSnapshot, mint: str) -> bool:
    return any(flag.active and flag.mint == mint and flag.triggers for flag in snapshot.emergencies)


def _recovery_triggers(
    intent: RiskIntent,
    limits: ShieldLimits,
    now: datetime,
) -> tuple[str, ...] | None:
    if intent.emergency is None:
        return None
    return assess_emergency(intent.emergency, limits, now)


def _halt_notice(snapshot: ShieldSnapshot, now: datetime) -> tuple[ShieldNotice, ...]:
    if snapshot.halt_entries:
        return (ShieldNotice("emergency", "entries_halted", now),)
    return ()


def _deny(
    snapshot: ShieldSnapshot,
    intent: RiskIntent,
    reason: str,
    now: datetime,
    *,
    allowed: Decimal | None = None,
    binding: str | None = None,
    notes: tuple[str, ...] = (),
    stop: Decimal | None = None,
    fill: Decimal | None = None,
    notices: tuple[ShieldNotice, ...] = (),
) -> Evaluation:
    del now
    return Evaluation(
        snapshot,
        False,
        reason,
        allowed,
        binding,
        notes,
        stop,
        fill,
        intent.exit_kind,
        notices,
    )


def _side(value: str) -> OrderSide:
    try:
        return OrderSide(value)
    except ValueError as exc:
        raise TradingValidationError("The order side is not a paper side.") from exc


def _exit_kind(value: str) -> ExitKind:
    try:
        return ExitKind(value)
    except ValueError as exc:
        raise TradingValidationError("The exit kind is not one Shield records.") from exc


def _security(value: str | None) -> SecurityPosture:
    if value is None:
        return SecurityPosture.UNKNOWN
    try:
        return SecurityPosture(value)
    except ValueError as exc:
        raise TradingValidationError(
            "Security posture must be clear, unknown, or restricted."
        ) from exc


def _tags(intent: RiskIntent) -> None:
    for value in (intent.creator, intent.narrative, intent.liquidity_provider, intent.driver):
        _clean_tag(value)


def _clean_tag(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    token = value.strip()
    if _TAG.fullmatch(token) is None:
        raise TradingValidationError("A correlation tag must be 1 to 48 letters, digits, _ or -.")
    if any(word in token.casefold() for word in _SECRET_WORDS):
        raise TradingValidationError("A correlation tag cannot be named like a secret.")
    return token


def _evidence_tags(intent: RiskIntent) -> tuple[str, ...] | None:
    tags = tuple(
        tag
        for tag in (
            _clean_tag(intent.creator),
            _clean_tag(intent.narrative),
            _clean_tag(intent.liquidity_provider),
            _clean_tag(intent.driver),
        )
        if tag is not None
    )
    if not tags:
        return None
    return tags


def _campaign_tags(campaign: CampaignRecord) -> tuple[str, ...] | None:
    tags = tuple(
        tag
        for tag in (
            campaign.creator,
            campaign.narrative,
            campaign.liquidity_provider,
            campaign.driver,
        )
        if tag
    )
    return tags or None


def _shares(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    folded_right = {item.casefold() for item in right}
    return any(item.casefold() in folded_right for item in left)


def _require_clock(value: datetime) -> None:
    if value.tzinfo is None:
        raise TradingValidationError("Shield times must include a timezone.")
