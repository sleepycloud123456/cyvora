"""Run one stored paper-trader pass and keep the decision log.

The historical strategy runner is unchanged. This worker uses the same
PaperBroker for orders. It does not sign, read a wallet, or import a
Nautilus fill.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from config.settings import Settings
from domain.enums import ExecutionMode
from domain.operations import TickResult
from domain.paper_trader import STRATEGY_ID, PoolQuote, RadarCandidate, TraderTick
from domain.shield import CampaignRecord
from readiness.guard import kill_switch_component, operator_orders_blocked
from trading.paper_trader.loop import run_once
from trading.paper_trader.quotes import refresh_pools
from trading.store import TradingStore

logger = logging.getLogger("cyvora.paper_trader")


class PaperTraderWorker:
    """One supervisor tick. It can submit a paper order through Shield."""

    kind = "paper_trader"

    def __init__(self, run: Callable[[datetime], TraderTick]) -> None:
        self._run = run

    def tick(self, now: datetime) -> TickResult:
        try:
            summary = self._run(now)
        except Exception as exc:
            return TickResult(
                self.kind,
                "failed",
                f"Paper trader failed ({type(exc).__name__}). No live order was sent.",
            )
        status = summary.status if summary.status in {"skipped", "not_configured"} else "ok"
        return TickResult(self.kind, status, summary.detail)


def run_stored(
    settings: Settings,
    now: datetime | None = None,
    *,
    entries_blocked: Callable[[], bool] | None = None,
) -> TraderTick:
    """Run one pass against PostgreSQL. A missing database submits nothing."""

    moment = now or datetime.now(UTC)
    if settings.execution_mode is not ExecutionMode.PAPER:
        tick = _plain(
            "skipped",
            "not_checked",
            "Read-only mode does not run the paper trader. Live trading stays locked.",
        )
        _record(settings, tick, moment)
        return tick
    if not settings.database_url:
        return _plain(
            "not_configured",
            "not_configured",
            "Paper trader storage is not configured. No order was submitted.",
        )
    from database.repositories.paper_trader import PostgresPaperTraderRepository
    from database.repositories.trading import PostgresTradingRepository

    store = PostgresTradingRepository(settings)
    blocked = (
        entries_blocked() if entries_blocked is not None else operator_orders_blocked(settings)
    )
    kill = _kill_word(settings)
    shield = store.load_shield()
    cycle_id, finished, candidates = PostgresPaperTraderRepository(settings).latest_candidates()
    quotes = _quotes(candidates, finished)
    fresh = _cycle_fresh(finished, moment, settings.paper_quote_max_age_seconds)
    extra = _mints_to_refresh(
        store,
        quotes,
        moment,
        settings.paper_quote_max_age_seconds,
        settings.paper_quote_limit,
    )
    if extra:
        refreshed = asyncio.run(
            refresh_pools(settings, extra, limit=settings.paper_quote_limit, now=moment)
        )
        quotes.update(refreshed)
        logger.info("paper pool quotes requested=%s stored=%s", len(extra), len(refreshed))
    repo = PostgresPaperTraderRepository(settings)
    open_mints = tuple(item.mint for item in store.list_positions() if item.quantity > 0)
    last_priced = repo.last_priced_at(open_mints) if open_mints else {}
    tick = run_once(
        mode=settings.execution_mode,
        store=store,
        candidates=candidates,
        quotes=quotes,
        cycle_id=cycle_id,
        quotes_fresh=fresh,
        bankroll=settings.paper_bankroll_sol,
        per_trade_fraction=settings.paper_per_trade_fraction,
        max_exposure_fraction=settings.paper_max_exposure_fraction,
        min_score=settings.paper_min_score,
        stop_fraction=settings.paper_stop_fraction,
        max_entries=settings.paper_max_entries_per_cycle,
        max_quote_age_seconds=settings.paper_quote_max_age_seconds,
        now=moment,
        entries_blocked=blocked,
        halt_entries=shield.halt_entries,
        kill_switch=kill,
        unpriced_writeoff_seconds=settings.paper_unpriced_writeoff_seconds,
        last_priced_at=last_priced,
    )
    _record(settings, tick, moment)
    return tick


def _record(settings: Settings, tick: TraderTick, now: datetime) -> None:
    if not settings.database_url:
        return
    from database.repositories.paper_trader import PostgresPaperTraderRepository

    PostgresPaperTraderRepository(settings).record(tick, now)


def _quotes(
    candidates: tuple[RadarCandidate, ...], finished: datetime | None
) -> dict[str, PoolQuote]:
    if finished is None:
        return {}
    observed = finished if finished.tzinfo is not None else finished.replace(tzinfo=UTC)
    return {
        item.mint: PoolQuote(
            item.mint,
            item.price,
            item.base_reserve,
            item.quote_reserve,
            observed,
        )
        for item in candidates
    }


def _cycle_fresh(finished: datetime | None, now: datetime, max_age: int) -> bool:
    if finished is None:
        return False
    observed = finished if finished.tzinfo is not None else finished.replace(tzinfo=UTC)
    if now.tzinfo is None:
        return False
    return (now - observed).total_seconds() <= max_age


def _mints_to_refresh(
    store: TradingStore,
    quotes: dict[str, PoolQuote],
    now: datetime,
    max_age: int,
    limit: int,
) -> tuple[str, ...]:
    if limit < 1:
        return ()
    shield = store.load_shield()
    needed: list[str] = []
    for position in store.list_positions():
        if position.quantity <= 0:
            continue
        campaign = _campaign(shield.campaigns, position.mint)
        if campaign is None or campaign.strategy_id != STRATEGY_ID:
            continue
        quote = quotes.get(position.mint)
        if quote is None or not _usable(quote, now, max_age):
            needed.append(position.mint)
        if len(needed) >= limit:
            break
    return tuple(needed)


def _usable(quote: PoolQuote, now: datetime, max_age: int) -> bool:
    if quote.base_reserve is None or quote.quote_reserve is None:
        return False
    if quote.base_reserve <= 0 or quote.quote_reserve <= 0 or quote.observed_at.tzinfo is None:
        return False
    return (now - quote.observed_at).total_seconds() <= max_age


def _campaign(campaigns: tuple[CampaignRecord, ...], mint: str) -> CampaignRecord | None:
    return next((item for item in campaigns if item.mint == mint and item.closed_at is None), None)


def _kill_word(settings: Settings) -> str:
    state = kill_switch_component(settings).state
    if state == "engaged":
        return "engaged"
    if state == "released":
        return "released"
    if state == "not_configured":
        return "not_configured"
    return "unreadable"


def _plain(status: str, kill_switch: str, detail: str) -> TraderTick:
    return TraderTick(
        status=status,
        kill_switch=kill_switch,
        halt_entries=False,
        entries_blocked=False,
        candidate_count=0,
        submitted_count=0,
        refused_count=0,
        detail=detail,
        decisions=(),
        equity_quote=None,
        realized_quote=None,
        unrealized_quote=None,
        open_positions=0,
    )
