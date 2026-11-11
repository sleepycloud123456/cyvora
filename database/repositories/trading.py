"""PostgreSQL paper ledger."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import Settings
from database.connection import create_database_engine
from database.models.trading import (
    TradingInstrument,
    TradingOrder,
    TradingOrderEvent,
    TradingPosition,
    TradingReconciliation,
    TradingStrategy,
)
from database.repositories.shield import (
    lock_snapshot,
    mark_campaign_reconciled,
    read_decisions,
    read_notices,
    read_snapshot,
    utc_now,
    write_snapshot,
)
from domain.exceptions import (
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    TradingDisabled,
    TradingValidationError,
)
from domain.shield import ShieldDecisionRecord, ShieldNotice, ShieldSnapshot
from domain.trading import (
    OrderRecord,
    OrderSide,
    OrderState,
    PositionRecord,
    ReconciliationRecord,
    ReconciliationStatus,
    SimulationOutcome,
    StrategyRecord,
    StrategyState,
    TradingSnapshot,
)
from shield.limits import require_paper_decision
from trading.store import LedgerContext, PaperBuilder, PaperCommit

logger = logging.getLogger("cyvora.trading")


def restore_strategies(settings: Settings) -> None:
    """Stop strategies left RUNNING by a previous process. Failure does not include the URL."""

    if not settings.database_url:
        return
    try:
        PostgresTradingRepository(settings).stop_running_strategies(datetime.now(UTC))
    except Exception as exc:
        logger.warning("strategy restore failed error_type=%s", type(exc).__name__)


class PostgresTradingRepository:
    """Insert paper history and read it back. One order is one transaction."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def commit_paper(
        self,
        idempotency_key: str,
        mint: str,
        build: PaperBuilder,
    ) -> OrderRecord:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                now = datetime.now(UTC)
                shield = lock_snapshot(session, now)
                existing_row = session.scalar(
                    select(TradingOrder)
                    .where(TradingOrder.idempotency_key == idempotency_key)
                    .with_for_update()
                )
                position_row = session.scalar(
                    select(TradingPosition).where(TradingPosition.mint == mint).with_for_update()
                )
                position_rows = session.scalars(select(TradingPosition)).all()
                order_rows = session.scalars(select(TradingOrder)).all()
                existing = None if existing_row is None else _order(existing_row)
                position = None if position_row is None else _position(position_row)
                commit = build(
                    LedgerContext(
                        existing=existing,
                        position=position,
                        positions=tuple(_position(row) for row in position_rows),
                        orders=tuple(_order(row) for row in order_rows),
                        shield=shield,
                    )
                )
                if existing is not None or commit.unchanged:
                    session.rollback()
                    return existing if existing is not None else commit.order
                _insert_commit(session, commit)
                if commit.shield is not None:
                    write_snapshot(
                        session, commit.shield, commit.shield_record, commit.notices, now
                    )
                session.commit()
                return commit.order
        except (
            DatabaseNotConfiguredError,
            DatabaseUnavailableError,
            TradingDisabled,
            TradingValidationError,
        ):
            raise
        except Exception as exc:
            logger.warning("paper persist failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The simulated order could not be stored.") from None
        finally:
            engine.dispose()

    def get_order(self, client_order_id: str) -> OrderRecord | None:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                row = session.scalar(
                    select(TradingOrder).where(TradingOrder.client_order_id == client_order_id)
                )
                return None if row is None else _order(row)
        except DatabaseNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("paper load failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The simulated order could not be read.") from None
        finally:
            engine.dispose()

    def save_reconciliation(
        self,
        order: OrderRecord,
        record: ReconciliationRecord,
        *,
        changed: bool,
    ) -> ReconciliationRecord:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                row = session.scalar(
                    select(TradingOrder)
                    .where(TradingOrder.client_order_id == order.client_order_id)
                    .with_for_update()
                )
                if row is None:
                    raise TradingValidationError("That paper order is not stored.")
                if changed:
                    row.state = order.state.value
                    row.reason = order.reason
                    row.updated_at = order.updated_at
                    session.add(
                        TradingOrderEvent(
                            order_id=row.id,
                            state=order.state.value,
                            note=record.detail[:300],
                            recorded_at=record.recorded_at,
                        )
                    )
                session.add(
                    TradingReconciliation(
                        client_order_id=record.client_order_id,
                        status=record.status.value,
                        detail=record.detail[:300],
                        recorded_at=record.recorded_at,
                    )
                )
                if record.status is ReconciliationStatus.MATCHED:
                    mark_campaign_reconciled(session, record.client_order_id)
                session.commit()
                return record
        except (DatabaseNotConfiguredError, TradingValidationError):
            raise
        except Exception as exc:
            logger.warning("reconciliation persist failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The reconciliation could not be stored.") from None
        finally:
            engine.dispose()

    def list_orders(self) -> tuple[OrderRecord, ...]:
        return self.snapshot().orders

    def list_positions(self) -> tuple[PositionRecord, ...]:
        return self.snapshot().positions

    def save_strategy(self, record: StrategyRecord) -> StrategyRecord:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                row = session.get(TradingStrategy, record.strategy_id)
                if row is None:
                    session.add(
                        TradingStrategy(
                            strategy_id=record.strategy_id,
                            name=record.name,
                            state=record.state.value,
                            parameters=dict(record.parameters),
                            registered_at=record.registered_at,
                            updated_at=record.updated_at,
                        )
                    )
                else:
                    row.name = record.name
                    row.state = record.state.value
                    row.parameters = dict(record.parameters)
                    row.updated_at = record.updated_at
                session.commit()
                return record
        except DatabaseNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("strategy persist failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The strategy could not be stored.") from None
        finally:
            engine.dispose()

    def get_strategy(self, strategy_id: str) -> StrategyRecord | None:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                row = session.get(TradingStrategy, strategy_id)
                return None if row is None else _strategy(row)
        except DatabaseNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("strategy load failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The strategy could not be read.") from None
        finally:
            engine.dispose()

    def list_strategies(self) -> tuple[StrategyRecord, ...]:
        return self.snapshot().strategies

    def stop_running_strategies(self, now: datetime) -> int:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                rows = session.scalars(
                    select(TradingStrategy).where(
                        TradingStrategy.state == StrategyState.RUNNING.value
                    )
                ).all()
                for row in rows:
                    row.state = StrategyState.STOPPED.value
                    row.updated_at = now
                session.commit()
                return len(rows)
        except DatabaseNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("strategy stop failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Running strategies could not be stopped.") from None
        finally:
            engine.dispose()

    def snapshot(self) -> TradingSnapshot:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                orders = tuple(
                    _order(row)
                    for row in session.scalars(select(TradingOrder).order_by(TradingOrder.id)).all()
                )
                positions = tuple(
                    _position(row)
                    for row in session.scalars(
                        select(TradingPosition).order_by(TradingPosition.mint)
                    ).all()
                )
                strategies = tuple(
                    _strategy(row)
                    for row in session.scalars(
                        select(TradingStrategy).order_by(TradingStrategy.strategy_id)
                    ).all()
                )
                return TradingSnapshot(orders, positions, strategies)
        except DatabaseNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("trading snapshot failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Stored simulation records could not be read.") from None
        finally:
            engine.dispose()

    def load_shield(self) -> ShieldSnapshot:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                return read_snapshot(session)
        except DatabaseNotConfiguredError:
            raise
        except TradingValidationError:
            raise
        except Exception as exc:
            logger.warning("shield load failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Stored Shield records could not be read.") from None
        finally:
            engine.dispose()

    def save_shield(
        self,
        snapshot: ShieldSnapshot,
        record: ShieldDecisionRecord | None = None,
        notices: tuple[ShieldNotice, ...] = (),
    ) -> None:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                now = utc_now()
                lock_snapshot(session, now)
                write_snapshot(session, snapshot, record, notices, now)
                session.commit()
        except (DatabaseNotConfiguredError, TradingValidationError):
            raise
        except Exception as exc:
            logger.warning("shield save failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("The Shield book could not be stored.") from None
        finally:
            engine.dispose()

    def list_notices(self) -> tuple[ShieldNotice, ...]:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                return read_notices(session)
        except DatabaseNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("shield notices failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Stored Shield notes could not be read.") from None
        finally:
            engine.dispose()

    def list_decisions(self) -> tuple[ShieldDecisionRecord, ...]:
        engine = create_database_engine(self._settings)
        try:
            with Session(engine) as session:
                return read_decisions(session)
        except DatabaseNotConfiguredError:
            raise
        except Exception as exc:
            logger.warning("shield decisions failed error_type=%s", type(exc).__name__)
            raise DatabaseUnavailableError("Stored Shield decisions could not be read.") from None
        finally:
            engine.dispose()


def _insert_commit(session: Session, commit: PaperCommit) -> None:
    instrument = commit.instrument
    if instrument is not None:
        current = session.scalar(
            select(TradingInstrument).where(TradingInstrument.mint == instrument.mint)
        )
        if current is None:
            session.add(
                TradingInstrument(
                    chain="sol",
                    mint=instrument.mint,
                    symbol=instrument.symbol,
                    size_decimals=instrument.size_decimals,
                    price_decimals=instrument.price_decimals,
                    quote_symbol=instrument.quote_symbol,
                    quote_decimals=instrument.quote_decimals,
                    created_at=commit.order.created_at,
                )
            )
        elif (
            current.size_decimals != instrument.size_decimals
            or current.price_decimals != instrument.price_decimals
            or current.quote_symbol != instrument.quote_symbol
            or current.quote_decimals != instrument.quote_decimals
        ):
            raise TradingValidationError("The stored instrument precision does not match.")
    order = commit.order
    row = TradingOrder(
        client_order_id=order.client_order_id,
        idempotency_key=order.idempotency_key,
        strategy_id=order.strategy_id,
        mint=order.mint,
        symbol=order.symbol,
        side=order.side.value,
        state=order.state.value,
        quantity=order.quantity,
        filled_quantity=order.filled_quantity,
        reference_price=order.reference_price,
        fill_price=order.fill_price,
        fee_quote=order.fee_quote,
        slippage_quote=order.slippage_quote,
        quote_symbol=order.quote_symbol,
        size_decimals=order.size_decimals,
        price_decimals=order.price_decimals,
        quote_decimals=order.quote_decimals,
        outcome=order.outcome.value,
        shield_decision=require_paper_decision(order.shield_decision, simulated=True),
        simulated=True,
        execution_mode="PAPER",
        reason=order.reason,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )
    session.add(row)
    session.flush()
    for event in commit.events:
        session.add(
            TradingOrderEvent(
                order_id=row.id,
                state=event.state_value,
                note=event.note[:300],
                recorded_at=event.recorded_at,
            )
        )
    if commit.position is not None:
        position = commit.position
        current_position = session.scalar(
            select(TradingPosition).where(TradingPosition.mint == position.mint)
        )
        if current_position is None:
            session.add(
                TradingPosition(
                    mint=position.mint,
                    quantity=position.quantity,
                    average_price=position.average_price,
                    cost_quote=position.cost_quote,
                    realized_pnl_quote=position.realized_pnl_quote,
                    quote_symbol=position.quote_symbol,
                    updated_at=position.updated_at,
                )
            )
        else:
            current_position.quantity = position.quantity
            current_position.average_price = position.average_price
            current_position.cost_quote = position.cost_quote
            current_position.realized_pnl_quote = position.realized_pnl_quote
            current_position.quote_symbol = position.quote_symbol
            current_position.updated_at = position.updated_at


def _order(row: TradingOrder) -> OrderRecord:
    return OrderRecord(
        client_order_id=row.client_order_id,
        idempotency_key=row.idempotency_key,
        strategy_id=row.strategy_id,
        mint=row.mint,
        symbol=row.symbol,
        side=OrderSide(row.side),
        state=OrderState(row.state),
        quantity=row.quantity,
        filled_quantity=row.filled_quantity,
        reference_price=row.reference_price,
        fill_price=row.fill_price,
        fee_quote=row.fee_quote,
        slippage_quote=row.slippage_quote,
        quote_symbol=row.quote_symbol,
        size_decimals=row.size_decimals,
        price_decimals=row.price_decimals,
        quote_decimals=row.quote_decimals,
        outcome=SimulationOutcome(row.outcome),
        shield_decision=row.shield_decision,
        simulated=row.simulated,
        reason=row.reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _position(row: TradingPosition) -> PositionRecord:
    return PositionRecord(
        mint=row.mint,
        quantity=row.quantity,
        average_price=row.average_price,
        cost_quote=row.cost_quote,
        realized_pnl_quote=row.realized_pnl_quote,
        quote_symbol=row.quote_symbol,
        updated_at=row.updated_at,
    )


def _strategy(row: TradingStrategy) -> StrategyRecord:
    payload = row.parameters if isinstance(row.parameters, dict) else {}
    parameters = tuple(
        sorted((str(key), str(value)) for key, value in payload.items() if isinstance(value, str))
    )
    return StrategyRecord(
        strategy_id=row.strategy_id,
        name=row.name,
        state=StrategyState(row.state),
        parameters=parameters,
        registered_at=row.registered_at,
        updated_at=row.updated_at,
    )
