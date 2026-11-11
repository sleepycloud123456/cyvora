"""PostgreSQL storage for simulation series and reports."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backtesting.history import bar_from_radar_candle, require_dataset
from backtesting.reports import dump_report
from config.settings import Settings
from database.connection import create_database_engine
from database.models.radar import LiquiditySnapshot, Token, TokenCandle
from database.models.simulation import (
    SimulationAssumption,
    SimulationBar,
    SimulationDataset,
    SimulationMember,
    SimulationRun,
    SimulationSignalRow,
)
from domain.exceptions import (
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    TradingValidationError,
)
from domain.simulation import (
    ExecutionAssumption,
    HistoricalBar,
    HistoricalDataset,
    HistoricalSignal,
    SimulationReport,
    UniverseMember,
)

logger = logging.getLogger("cyvora.simulation")


class PostgresSimulationRepository:
    """Insert simulation history. A run cannot mark its parameters as deployed."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def save_dataset(self, dataset: HistoricalDataset, now: datetime) -> HistoricalDataset:
        checked = require_dataset(dataset)
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                if session.get(SimulationDataset, checked.dataset_id) is not None:
                    raise TradingValidationError("That dataset id is already stored.")
                session.add(
                    SimulationDataset(
                        dataset_id=checked.dataset_id,
                        name=checked.name,
                        source=checked.source,
                        selection_note=checked.selection_note,
                        limitations=list(checked.limitations),
                        created_at=now,
                        live_trading_enabled=False,
                    )
                )
                for bar in checked.bars:
                    session.add(_bar_row(checked.dataset_id, bar))
                for signal in checked.signals:
                    session.add(
                        SimulationSignalRow(
                            dataset_id=checked.dataset_id,
                            mint=signal.mint,
                            observed_at=signal.observed_at,
                            name=signal.name,
                            reference=signal.reference,
                        )
                    )
                for member in checked.members:
                    session.add(
                        SimulationMember(
                            dataset_id=checked.dataset_id,
                            mint=member.mint,
                            included=member.included,
                            reason=member.reason,
                        )
                    )
                session.commit()
                return checked
        except (DatabaseNotConfiguredError, DatabaseUnavailableError, TradingValidationError):
            raise
        except Exception as exc:
            logger.warning("simulation dataset failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The simulation dataset could not be stored.") from None
        finally:
            engine.dispose()

    def get_dataset(self, dataset_id: str) -> HistoricalDataset | None:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                row = session.get(SimulationDataset, dataset_id)
                if row is None:
                    return None
                bars = session.scalars(
                    select(SimulationBar)
                    .where(SimulationBar.dataset_id == dataset_id)
                    .order_by(SimulationBar.observed_at, SimulationBar.mint)
                ).all()
                signals = session.scalars(
                    select(SimulationSignalRow).where(SimulationSignalRow.dataset_id == dataset_id)
                ).all()
                members = session.scalars(
                    select(SimulationMember).where(SimulationMember.dataset_id == dataset_id)
                ).all()
                return HistoricalDataset(
                    dataset_id=row.dataset_id,
                    name=row.name,
                    source=row.source,
                    selection_note=row.selection_note,
                    bars=tuple(_bar(item) for item in bars),
                    signals=tuple(
                        HistoricalSignal(item.mint, item.observed_at, item.name, item.reference)
                        for item in signals
                    ),
                    members=tuple(
                        UniverseMember(item.mint, item.included, item.reason) for item in members
                    ),
                    limitations=tuple(row.limitations),
                )
        except (DatabaseNotConfiguredError, DatabaseUnavailableError, TradingValidationError):
            raise
        except Exception as exc:
            logger.warning("simulation read failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The simulation dataset could not be read.") from None
        finally:
            engine.dispose()

    def list_datasets(self) -> tuple[tuple[str, str], ...]:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                rows = session.scalars(
                    select(SimulationDataset).order_by(SimulationDataset.created_at)
                ).all()
                return tuple((row.dataset_id, row.name) for row in rows)
        except (DatabaseNotConfiguredError, DatabaseUnavailableError):
            raise
        except Exception as exc:
            logger.warning("simulation list failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Simulation datasets could not be read.") from None
        finally:
            engine.dispose()

    def save_run(self, report: SimulationReport) -> None:
        if report.parameters_deployed:
            raise TradingValidationError("A simulation cannot deploy parameters.")
        payload = dump_report(report)
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                if session.get(SimulationRun, report.run_id) is not None:
                    raise TradingValidationError("That simulation run is already stored.")
                session.add(
                    SimulationRun(
                        run_id=report.run_id,
                        dataset_id=report.dataset_id,
                        kind=report.kind,
                        strategy_id=report.strategy_id,
                        created_at=report.created_at,
                        report_json=payload,
                        parameters_deployed=False,
                        live_trading_enabled=False,
                    )
                )
                session.commit()
        except (DatabaseNotConfiguredError, DatabaseUnavailableError, TradingValidationError):
            raise
        except Exception as exc:
            logger.warning("simulation run failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The simulation report could not be stored.") from None
        finally:
            engine.dispose()

    def list_runs(self) -> tuple[dict[str, object], ...]:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                rows = session.scalars(
                    select(SimulationRun).order_by(SimulationRun.created_at)
                ).all()
                return tuple(dict(row.report_json) for row in rows)
        except (DatabaseNotConfiguredError, DatabaseUnavailableError):
            raise
        except Exception as exc:
            logger.warning("simulation reports failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Simulation reports could not be read.") from None
        finally:
            engine.dispose()

    def save_assumption(self, row: ExecutionAssumption, now: datetime) -> None:
        if row.live_trading_enabled or not row.simulated:
            raise TradingValidationError("A paper assumption cannot enable live trading.")
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                session.merge(
                    SimulationAssumption(
                        client_order_id=row.client_order_id,
                        model=row.model,
                        impact=row.impact,
                        fee_quote=row.fee_quote,
                        slippage_quote=row.slippage_quote,
                        delay_seconds=row.delay_seconds,
                        limitations=list(row.limitations),
                        recorded_at=now,
                        simulated=True,
                        live_trading_enabled=False,
                    )
                )
                session.commit()
        except (DatabaseNotConfiguredError, DatabaseUnavailableError, TradingValidationError):
            raise
        except Exception as exc:
            logger.warning("simulation assumption failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The paper assumption could not be stored.") from None
        finally:
            engine.dispose()

    def list_assumptions(self) -> tuple[ExecutionAssumption, ...]:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                rows = session.scalars(
                    select(SimulationAssumption).order_by(SimulationAssumption.recorded_at)
                ).all()
                return tuple(_assumption(row) for row in rows)
        except (DatabaseNotConfiguredError, DatabaseUnavailableError):
            raise
        except Exception as exc:
            logger.warning("simulation assumptions failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Paper assumptions could not be read.") from None
        finally:
            engine.dispose()

    def import_radar(
        self,
        dataset_id: str,
        mint: str,
        selection_note: str,
        now: datetime,
    ) -> HistoricalDataset:
        """Copy stored radar candles. This does not call GMGN."""

        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                token = session.scalar(select(Token).where(Token.address == mint))
                bars: list[HistoricalBar] = []
                limitations = [
                    "gmgn_candle_volume_is_not_base_size",
                    "candle_close_is_not_a_fill",
                ]
                if token is None:
                    members = (
                        UniverseMember(mint, True, "No stored radar candles for this mint."),
                    )
                else:
                    candles = session.scalars(
                        select(TokenCandle)
                        .where(TokenCandle.token_id == token.id)
                        .order_by(TokenCandle.candle_time)
                    ).all()
                    if len(candles) > 400:
                        limitations.append("radar_import_kept_the_oldest_400_candles")
                    snapshots = session.scalars(
                        select(LiquiditySnapshot)
                        .where(LiquiditySnapshot.token_id == token.id)
                        .order_by(LiquiditySnapshot.retrieved_at)
                    ).all()
                    seen_times: set[datetime] = set()
                    for candle in candles[:400]:
                        snapshot = _snapshot_at(snapshots, candle.candle_time)
                        evidence = () if snapshot is None else _evidence(snapshot.evidence)
                        adapted, notes = bar_from_radar_candle(
                            mint=mint,
                            symbol=(token.symbol or "TOKEN")[:32],
                            candle_time=candle.candle_time,
                            open_price=candle.open,
                            high=candle.high,
                            low=candle.low,
                            close=candle.close,
                            volume=candle.volume,
                            evidence=evidence,
                            snapshot_at=None if snapshot is None else snapshot.retrieved_at,
                        )
                        limitations.extend(notes)
                        if adapted is None or adapted.observed_at in seen_times:
                            if adapted is not None:
                                limitations.append("duplicate_radar_candle_time_skipped")
                            continue
                        seen_times.add(adapted.observed_at)
                        bars.append(adapted)
                    members = (
                        UniverseMember(
                            mint, True, "Stored radar candles only. Missing mints stay missing."
                        ),
                    )
                dataset = HistoricalDataset(
                    dataset_id=dataset_id,
                    name=f"Radar {mint[:8]}",
                    source="radar_candle",
                    selection_note=selection_note,
                    bars=tuple(bars),
                    signals=(),
                    members=members,
                    limitations=tuple(dict.fromkeys(limitations)),
                )
        except (DatabaseNotConfiguredError, DatabaseUnavailableError, TradingValidationError):
            raise
        except Exception as exc:
            logger.warning("radar import failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Stored radar candles could not be read.") from None
        finally:
            engine.dispose()
        return self.save_dataset(dataset, now)


def _bar_row(dataset_id: str, bar: HistoricalBar) -> SimulationBar:
    return SimulationBar(
        dataset_id=dataset_id,
        mint=bar.mint,
        symbol=bar.symbol,
        observed_at=bar.observed_at,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume_quote=bar.volume_quote,
        base_volume=bar.base_volume,
        base_reserve=bar.base_reserve,
        quote_reserve=bar.quote_reserve,
        bid=bar.bid,
        ask=bar.ask,
        bid_size=bar.bid_size,
        ask_size=bar.ask_size,
        source=bar.source,
        security=bar.security,
        creator=bar.creator,
        volatility=bar.volatility,
        token_age_seconds=bar.token_age_seconds,
        market_condition=bar.market_condition,
    )


def _bar(row: SimulationBar) -> HistoricalBar:
    return HistoricalBar(
        mint=row.mint,
        symbol=row.symbol,
        observed_at=row.observed_at,
        source=row.source,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume_quote=row.volume_quote,
        base_volume=row.base_volume,
        base_reserve=row.base_reserve,
        quote_reserve=row.quote_reserve,
        bid=row.bid,
        ask=row.ask,
        bid_size=row.bid_size,
        ask_size=row.ask_size,
        security=row.security,
        creator=row.creator,
        volatility=row.volatility,
        token_age_seconds=row.token_age_seconds,
        market_condition=row.market_condition,
    )


def _assumption(row: SimulationAssumption) -> ExecutionAssumption:
    return ExecutionAssumption(
        client_order_id=row.client_order_id,
        model=row.model,
        impact=row.impact,
        fee_quote=row.fee_quote,
        slippage_quote=row.slippage_quote,
        delay_seconds=row.delay_seconds,
        limitations=tuple(row.limitations),
        simulated=True,
        live_trading_enabled=False,
    )


def _evidence(raw: list[list[str]]) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for item in raw:
        if len(item) >= 2:
            pairs.append((str(item[0]), str(item[1])))
    return tuple(pairs)


def _snapshot_at(
    snapshots: Sequence[LiquiditySnapshot], candle_time: int | None
) -> LiquiditySnapshot | None:
    if candle_time is None:
        return None
    seconds = candle_time // 1000 if candle_time >= 100_000_000_000 else candle_time
    moment = datetime.fromtimestamp(seconds, UTC)
    chosen: LiquiditySnapshot | None = None
    for snapshot in snapshots:
        if snapshot.retrieved_at <= moment:
            chosen = snapshot
    return chosen
