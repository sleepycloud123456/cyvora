"""PostgreSQL log for the autonomous paper trader.

Orders and positions stay in the trading tables. This store records why a
candidate was taken or rejected, plus the virtual equity point. A row cannot
enable live trading.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import Settings
from database.connection import create_database_engine
from database.models.paper_trader import PaperTraderCycle, PaperTraderDecision, PaperTraderEquity
from database.models.radar import RadarCycle, Token, TokenAnalysis
from domain.exceptions import (
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    TradingValidationError,
)
from domain.paper_trader import (
    PaperTraderView,
    PoolQuote,
    RadarCandidate,
    StoredTraderCycle,
    StoredTraderDecision,
    TraderDecision,
    TraderTick,
)
from terminal.paper_trader import build_paper_trader_view
from trading.paper_trader.candidates import candidate_from_analysis

logger = logging.getLogger("cyvora.paper_trader")

_ACTIONS = frozenset(
    {"submitted", "refused", "blocked", "held", "duplicate", "skipped", "exited"}
)
_UNPRICED_REASONS = frozenset({"mark_missing", "mark_stale", "pool_reserves_missing"})
_STATUSES = frozenset({"running", "paused", "blocked", "skipped", "failed"})
_KILL = frozenset({"released", "engaged", "unreadable", "not_configured", "not_checked"})


class PostgresPaperTraderRepository:
    """Append one pass and read it back for the dashboard."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def record(self, tick: TraderTick, now: datetime) -> None:
        if tick.decisions and any(item.live_trading_enabled for item in tick.decisions):
            raise TradingValidationError("A paper trader decision cannot enable live trading.")
        if tick.status not in _STATUSES or tick.kill_switch not in _KILL:
            raise TradingValidationError("That paper trader status cannot be stored.")
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                cycle = PaperTraderCycle(
                    started_at=now,
                    finished_at=now,
                    status=tick.status,
                    kill_switch=tick.kill_switch,
                    halt_entries=tick.halt_entries,
                    entries_blocked=tick.entries_blocked,
                    candidate_count=tick.candidate_count,
                    submitted_count=tick.submitted_count,
                    refused_count=tick.refused_count,
                    detail=tick.detail[:500],
                    live_trading_enabled=False,
                )
                session.add(cycle)
                session.flush()
                for decision in tick.decisions:
                    session.add(_decision_row(cycle.id, decision, now))
                session.add(
                    PaperTraderEquity(
                        cycle_id=cycle.id,
                        observed_at=now,
                        equity_quote=tick.equity_quote,
                        realized_quote=tick.realized_quote,
                        unrealized_quote=tick.unrealized_quote,
                        open_positions=tick.open_positions,
                        live_trading_enabled=False,
                    )
                )
                session.commit()
        except (DatabaseNotConfiguredError, DatabaseUnavailableError, TradingValidationError):
            raise
        except Exception as exc:
            logger.warning("paper trader record failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The paper trader log could not be stored.") from None
        finally:
            engine.dispose()

    def latest_pool_quotes(
        self, mints: tuple[str, ...]
    ) -> dict[str, tuple[PoolQuote, int]]:
        """Latest stored radar pool snapshot for each mint, with its cycle id."""

        if not mints:
            return {}
        engine = create_database_engine(self._settings)
        found: dict[str, tuple[PoolQuote, int]] = {}
        try:
            with Session(engine) as session:
                rows = session.execute(
                    select(Token, TokenAnalysis, RadarCycle)
                    .join(TokenAnalysis, Token.id == TokenAnalysis.token_id)
                    .join(RadarCycle, RadarCycle.id == TokenAnalysis.cycle_id)
                    .where(Token.address.in_(mints))
                    .order_by(
                        Token.address,
                        RadarCycle.finished_at.desc(),
                        TokenAnalysis.id.desc(),
                    )
                ).all()
                for token, analysis, cycle in rows:
                    if token.address in found:
                        continue
                    candidate = candidate_from_analysis(
                        token.address,
                        token.symbol,
                        analysis.total_score,
                        analysis.lifecycle,
                        analysis.freshness,
                        analysis.security_category,
                        analysis.breakdown,
                    )
                    finished = cycle.finished_at
                    if finished.tzinfo is None:
                        finished = finished.replace(tzinfo=UTC)
                    found[token.address] = (
                        PoolQuote(
                            token.address,
                            candidate.price,
                            candidate.base_reserve,
                            candidate.quote_reserve,
                            finished,
                        ),
                        cycle.id,
                    )
        except (DatabaseNotConfiguredError, DatabaseUnavailableError):
            raise
        except Exception as exc:
            logger.warning("paper trader stored quotes failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Stored radar pool quotes could not be read.") from None
        finally:
            engine.dispose()
        return found

    def last_priced_at(self, mints: tuple[str, ...]) -> dict[str, datetime]:
        """Latest time each mint had a usable mark, inferred from stored history."""

        if not mints:
            return {}
        engine = create_database_engine(self._settings)
        found: dict[str, datetime] = {}
        try:
            with Session(engine) as session:
                rows = session.scalars(
                    select(PaperTraderDecision)
                    .where(PaperTraderDecision.mint.in_(mints))
                    .where(PaperTraderDecision.reason.not_in(_UNPRICED_REASONS))
                    .order_by(PaperTraderDecision.created_at.desc())
                ).all()
                for row in rows:
                    if row.mint in found:
                        continue
                    found[row.mint] = _aware_time(row.created_at)
                equity = session.scalar(
                    select(PaperTraderEquity)
                    .where(PaperTraderEquity.equity_quote.is_not(None))
                    .order_by(PaperTraderEquity.observed_at.desc())
                    .limit(1)
                )
                if equity is not None:
                    observed = _aware_time(equity.observed_at)
                    for mint in mints:
                        if mint not in found:
                            found[mint] = observed
        except (DatabaseNotConfiguredError, DatabaseUnavailableError):
            raise
        except Exception as exc:
            logger.warning("paper trader last priced read failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Stored paper marks could not be read.") from None
        finally:
            engine.dispose()
        return found

    def latest_candidates(self) -> tuple[int | None, datetime | None, tuple[RadarCandidate, ...]]:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                cycle = session.scalar(select(RadarCycle).order_by(RadarCycle.id.desc()).limit(1))
                if cycle is None:
                    return None, None, ()
                rows = session.scalars(
                    select(TokenAnalysis)
                    .where(TokenAnalysis.cycle_id == cycle.id)
                    .order_by(TokenAnalysis.rank_position)
                ).all()
                found: list[RadarCandidate] = []
                for analysis in rows:
                    token = session.get(Token, analysis.token_id)
                    if token is None:
                        continue
                    found.append(
                        candidate_from_analysis(
                            token.address,
                            token.symbol,
                            analysis.total_score,
                            analysis.lifecycle,
                            analysis.freshness,
                            analysis.security_category,
                            analysis.breakdown,
                        )
                    )
                finished = cycle.finished_at
                if finished.tzinfo is None:
                    finished = finished.replace(tzinfo=UTC)
                return cycle.id, finished, tuple(found)
        except (DatabaseNotConfiguredError, DatabaseUnavailableError):
            raise
        except Exception as exc:
            logger.warning("paper trader radar read failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Stored radar candidates could not be read.") from None
        finally:
            engine.dispose()

    def load_view(
        self, now: datetime, *, stale_after_seconds: int, bankroll: Decimal
    ) -> PaperTraderView:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                cycle = session.scalar(
                    select(PaperTraderCycle).order_by(PaperTraderCycle.id.desc()).limit(1)
                )
                decisions = session.scalars(
                    select(PaperTraderDecision).order_by(PaperTraderDecision.id.desc()).limit(12)
                ).all()
                points = session.scalars(
                    select(PaperTraderEquity).order_by(PaperTraderEquity.id.desc()).limit(60)
                ).all()
                stored = _stored_cycle(cycle)
                decision_rows = tuple(_stored_decision(item) for item in decisions)
                equity = tuple(item.equity_quote for item in reversed(points))
        except DatabaseNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("paper trader view failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The paper trader log could not be read.") from None
        finally:
            engine.dispose()
        return build_paper_trader_view(
            stored,
            decision_rows,
            equity,
            now=now,
            stale_after_seconds=stale_after_seconds,
            bankroll=bankroll,
        )


def _stored_cycle(cycle: PaperTraderCycle | None) -> StoredTraderCycle | None:
    if cycle is None:
        return None
    finished = cycle.finished_at
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=UTC)
    return StoredTraderCycle(
        status=cycle.status,
        kill_switch=cycle.kill_switch,
        halt_entries=cycle.halt_entries,
        entries_blocked=cycle.entries_blocked,
        detail=cycle.detail,
        finished_at=finished,
    )


def _stored_decision(row: PaperTraderDecision) -> StoredTraderDecision:
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return StoredTraderDecision(
        symbol=row.symbol,
        action=row.action,
        reason=row.reason,
        score=row.score,
        created_at=created,
    )


def _decision_row(cycle_id: int, decision: TraderDecision, now: datetime) -> PaperTraderDecision:
    if decision.action not in _ACTIONS:
        raise TradingValidationError("That paper trader action cannot be stored.")
    if decision.live_trading_enabled:
        raise TradingValidationError("A paper trader decision cannot enable live trading.")
    return PaperTraderDecision(
        cycle_id=cycle_id,
        mint=decision.mint[:64],
        symbol=decision.symbol[:32],
        action=decision.action,
        reason=decision.reason[:240],
        score=None if decision.score is None else decision.score[:32],
        client_order_id=decision.client_order_id,
        created_at=now,
        live_trading_enabled=False,
    )


def _aware_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
