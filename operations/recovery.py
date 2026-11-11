"""Paper-book recovery. A missing wallet read is not a flat wallet."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from config.settings import Settings
from domain.operations import (
    TERMINAL_ORDER_STATES,
    WALLET_NOT_AUTHORIZED,
    BookOrder,
    BookPosition,
    BookSnapshot,
    RecoveryReport,
)

logger = logging.getLogger("cyvora.operations")

_WALLET_SENTENCE = "Wallet balances were not read and were not assumed flat."


def assess_book(book: BookSnapshot, started_at: datetime, finished_at: datetime) -> RecoveryReport:
    """Decide whether new paper entries can continue."""

    if book.database_state == "not_configured":
        return _report(
            result="no_persisted_book",
            book=book,
            pending=None,
            open_positions=None,
            unresolved=None,
            position_status="unread",
            running=None,
            entries_blocked=False,
            detail=f"No database is configured. {_WALLET_SENTENCE}",
            started_at=started_at,
            finished_at=finished_at,
        )
    if book.database_state != "reachable":
        return _report(
            result="blocked",
            book=book,
            pending=None,
            open_positions=None,
            unresolved=None,
            position_status="unread",
            running=None,
            entries_blocked=True,
            detail=(
                "The paper book could not be read. New paper entries stay blocked. "
                f"{_WALLET_SENTENCE}"
            ),
            started_at=started_at,
            finished_at=finished_at,
        )
    pending = _pending(book.orders)
    conflict = _positions_conflict(book.orders, book.positions)
    open_positions = sum(1 for position in book.positions if position.quantity != 0)
    blocked = pending > 0 or conflict or book.running_strategies > 0
    if blocked:
        detail = (
            f"New paper entries stay blocked until the paper book is consistent. {_WALLET_SENTENCE}"
        )
        position_status = "conflict" if conflict else "matched"
        result = "blocked"
    else:
        detail = f"The paper book matches confirmed fills. {_WALLET_SENTENCE}"
        position_status = "matched"
        result = "complete"
    return _report(
        result=result,
        book=book,
        pending=pending,
        open_positions=open_positions,
        unresolved=pending,
        position_status=position_status,
        running=book.running_strategies,
        entries_blocked=blocked,
        detail=detail,
        started_at=started_at,
        finished_at=finished_at,
    )


def startup_recovery(
    settings: Settings,
    *,
    now: datetime | None = None,
    reader: Callable[[], BookSnapshot] | None = None,
    saver: Callable[[RecoveryReport], None] | None = None,
) -> RecoveryReport:
    """Load the persisted book once. Failure blocks entries and omits the driver text."""

    started = now or datetime.now(UTC)
    if not settings.database_url:
        report = assess_book(
            BookSnapshot("not_configured", "unread", (), (), 0, None),
            started,
            started,
        )
        return report
    load = reader or (lambda: _read_book(settings))
    try:
        book = load()
    except Exception as exc:
        logger.warning("recovery read failed error_type=%s", type(exc).__name__)
        book = BookSnapshot("unreachable", "unread", (), (), 0, None)
    finished = now or datetime.now(UTC)
    report = assess_book(book, started, finished)
    _store(settings, report, saver)
    return report


def _read_book(settings: Settings) -> BookSnapshot:
    from database.repositories.operations import read_book

    return read_book(settings)


def _store(
    settings: Settings,
    report: RecoveryReport,
    saver: Callable[[RecoveryReport], None] | None,
) -> None:
    if report.database_state != "reachable":
        return
    save = saver
    if save is None:
        from database.repositories.operations import PostgresOperationsRepository

        save = PostgresOperationsRepository(settings).save_recovery
    try:
        save(report)
    except Exception as exc:
        logger.warning("recovery store failed error_type=%s", type(exc).__name__)


def _pending(orders: tuple[BookOrder, ...]) -> int:
    return sum(1 for order in orders if order.state not in TERMINAL_ORDER_STATES)


def _positions_conflict(orders: tuple[BookOrder, ...], positions: tuple[BookPosition, ...]) -> bool:
    fills: dict[str, Decimal] = {}
    for order in orders:
        if order.state != "CONFIRMED":
            continue
        signed = order.filled_quantity if order.side == "BUY" else -order.filled_quantity
        fills[order.mint] = fills.get(order.mint, Decimal(0)) + signed
    seen: set[str] = set()
    for position in positions:
        seen.add(position.mint)
        if position.quantity != fills.get(position.mint, Decimal(0)):
            return True
    return any(mint not in seen and total != 0 for mint, total in fills.items())


def _report(
    *,
    result: str,
    book: BookSnapshot,
    pending: int | None,
    open_positions: int | None,
    unresolved: int | None,
    position_status: str,
    running: int | None,
    entries_blocked: bool,
    detail: str,
    started_at: datetime,
    finished_at: datetime,
) -> RecoveryReport:
    return RecoveryReport(
        result=result,
        database_state=book.database_state,
        risk_state=book.risk_state,
        pending_orders=pending,
        open_positions=open_positions,
        unresolved_orders=unresolved,
        position_status=position_status,
        running_strategies=running,
        entries_blocked=entries_blocked,
        wallet_reconciliation=WALLET_NOT_AUTHORIZED,
        wallet_assumed_flat=False,
        live_trading_enabled=False,
        detail=detail,
        started_at=started_at,
        finished_at=finished_at,
    )
