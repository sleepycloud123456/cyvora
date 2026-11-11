"""Compare a stored paper order with a report. A mismatch does not retry."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from domain.trading import (
    ExecutionReport,
    OrderRecord,
    OrderState,
    ReconciliationRecord,
    ReconciliationStatus,
)


def reconcile_order(
    order: OrderRecord,
    report: ExecutionReport | None,
    now: datetime,
) -> tuple[OrderRecord, ReconciliationRecord]:
    """Match, or mark the order unknown without changing its position."""

    if report is None:
        updated = replace(order, state=OrderState.UNKNOWN, reason="report_missing", updated_at=now)
        return updated, ReconciliationRecord(
            client_order_id=order.client_order_id,
            status=ReconciliationStatus.UNKNOWN,
            detail="No execution report was supplied. The order was not retried.",
            recorded_at=now,
        )
    matches = (
        report.client_order_id == order.client_order_id
        and report.state == order.state
        and report.filled_quantity == order.filled_quantity
        and report.fill_price == order.fill_price
    )
    if matches:
        return order, ReconciliationRecord(
            client_order_id=order.client_order_id,
            status=ReconciliationStatus.MATCHED,
            detail="The report matches the stored order.",
            recorded_at=now,
        )
    updated = replace(order, state=OrderState.UNKNOWN, reason="report_conflict", updated_at=now)
    return updated, ReconciliationRecord(
        client_order_id=order.client_order_id,
        status=ReconciliationStatus.CONFLICT,
        detail=(
            "The report does not match the stored order. "
            "The position was not changed and the order was not retried."
        ),
        recorded_at=now,
    )


def reconcile_position(quantity: Decimal, signed_fill_total: Decimal) -> ReconciliationStatus:
    """Compare a position quantity with the sum of confirmed fill quantities."""

    if quantity == signed_fill_total:
        return ReconciliationStatus.MATCHED
    return ReconciliationStatus.CONFLICT
