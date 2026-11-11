"""Paper execution gateway.

A fill is an explicit simulator result at a caller-supplied price. It does
not call GMGN, a signer, or a Solana RPC. Read-only mode stores nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from domain.enums import ExecutionMode
from domain.exceptions import TradingDisabled, TradingValidationError
from domain.trading import (
    SHIELD_NOT_AUTHORIZED,
    ExecutionReport,
    OrderRecord,
    OrderSide,
    OrderState,
    PositionRecord,
    ReconciliationRecord,
    SimulationOutcome,
    SolanaInstrument,
)
from trading.execution.idempotency import client_order_id_for, require_idempotency_key
from trading.execution.order_manager import paper_states
from trading.execution.reconciliation import reconcile_order
from trading.instruments import (
    require_instrument,
    require_non_negative,
    require_positive,
    require_scaled,
)
from trading.portfolio.accounting import apply_fill
from trading.store import OrderEventWrite, PaperCommit, TradingStore

_NOTES = {
    OrderState.CREATED: "TradeIntentCreated. Shield has not authorized this intent.",
    OrderState.VALIDATED: "The paper request passed local validation.",
    OrderState.SIMULATION_PENDING: "ExecutionPending. The local simulator has not finished.",
    OrderState.SIMULATION_PASSED: (
        "PaperOrderSubmitted. The local simulator accepted the order. "
        "No venue and no chain transaction was used."
    ),
    OrderState.CONFIRMED: (
        "ExecutionConfirmed. This is a simulator result, not a chain confirmation."
    ),
    OrderState.FAILED: "ExecutionFailed. No position change was stored.",
}


class PaperOrderRequest:
    """One simulated order. ``shield_approved`` must stay false."""

    def __init__(
        self,
        *,
        strategy_id: str,
        instrument: SolanaInstrument,
        side: OrderSide,
        quantity: Decimal,
        reference_price: Decimal,
        outcome: SimulationOutcome,
        idempotency_key: str,
        fill_quantity: Decimal | None = None,
        fee_quote: Decimal = Decimal(0),
        slippage_quote: Decimal = Decimal(0),
        shield_approved: bool = False,
    ) -> None:
        self.strategy_id = strategy_id
        self.instrument = instrument
        self.side = side
        self.quantity = quantity
        self.reference_price = reference_price
        self.outcome = outcome
        self.idempotency_key = idempotency_key
        self.fill_quantity = fill_quantity
        self.fee_quote = fee_quote
        self.slippage_quote = slippage_quote
        self.shield_approved = shield_approved


class PaperExecutionGateway:
    """Record paper orders. Live submission is a separate method that always raises."""

    def __init__(
        self,
        mode: ExecutionMode,
        store: TradingStore,
        clock: Callable[[], datetime],
    ) -> None:
        self._mode = mode
        self._store = store
        self._clock = clock

    def submit(self, request: PaperOrderRequest) -> OrderRecord:
        self._require_paper()
        if request.shield_approved:
            raise TradingDisabled(
                "A strategy cannot approve an order. Shield is not implemented "
                "and live execution is disabled."
            )
        key = require_idempotency_key(request.idempotency_key)
        instrument = require_instrument(request.instrument)
        self._validate(request, instrument)
        return self._store.commit_paper(
            key,
            instrument.mint,
            lambda existing, position: self._build(request, instrument, key, existing, position),
        )

    def reconcile(
        self,
        client_order_id: str,
        report: ExecutionReport | None,
    ) -> ReconciliationRecord:
        """Compare a stored order with a report. The position is left as it was."""

        order = self._store.get_order(client_order_id)
        if order is None:
            raise TradingValidationError("That paper order is not stored.")
        updated, record = reconcile_order(order, report, self._clock())
        changed = updated.state != order.state or updated.reason != order.reason
        return self._store.save_reconciliation(updated, record, changed=changed)

    def _require_paper(self) -> None:
        if self._mode is not ExecutionMode.PAPER:
            raise TradingDisabled(
                "Read-only mode does not store simulated orders. Live execution is disabled."
            )

    def _validate(self, request: PaperOrderRequest, instrument: SolanaInstrument) -> None:
        require_positive(request.quantity, "Quantity")
        require_positive(request.reference_price, "Reference price")
        require_non_negative(request.fee_quote, "Fee")
        require_non_negative(request.slippage_quote, "Slippage")
        require_scaled(request.quantity, instrument.size_decimals, "Quantity")
        require_scaled(request.reference_price, instrument.price_decimals, "Reference price")
        require_scaled(request.fee_quote, instrument.quote_decimals, "Fee")
        require_scaled(request.slippage_quote, instrument.quote_decimals, "Slippage")
        if request.outcome is SimulationOutcome.PARTIAL:
            if request.fill_quantity is None:
                raise TradingValidationError("A partial paper fill needs a fill quantity.")
            require_positive(request.fill_quantity, "Fill quantity")
            require_scaled(request.fill_quantity, instrument.size_decimals, "Fill quantity")
            if request.fill_quantity >= request.quantity:
                raise TradingValidationError("A partial fill must be smaller than the order.")
        elif request.fill_quantity is not None:
            raise TradingValidationError("Fill quantity is only used for a partial outcome.")

    def _build(
        self,
        request: PaperOrderRequest,
        instrument: SolanaInstrument,
        key: str,
        existing: OrderRecord | None,
        position: PositionRecord | None,
    ) -> PaperCommit:
        if existing is not None:
            return PaperCommit(existing, (), None, None, True)
        now = self._clock()
        filled, fill_price, reason = self._result(request, instrument, position, now)
        outcome = request.outcome if reason is None else SimulationOutcome.FAIL
        states = paper_states(outcome)
        events = tuple(OrderEventWrite(state.value, _NOTES[state], now) for state in states)
        order = OrderRecord(
            client_order_id=client_order_id_for(key),
            idempotency_key=key,
            strategy_id=request.strategy_id,
            mint=instrument.mint,
            symbol=instrument.symbol,
            side=request.side,
            state=states[-1],
            quantity=request.quantity,
            filled_quantity=filled,
            reference_price=request.reference_price,
            fill_price=fill_price,
            fee_quote=request.fee_quote if filled > 0 else Decimal(0),
            slippage_quote=request.slippage_quote if filled > 0 else Decimal(0),
            quote_symbol=instrument.quote_symbol,
            size_decimals=instrument.size_decimals,
            price_decimals=instrument.price_decimals,
            quote_decimals=instrument.quote_decimals,
            outcome=request.outcome,
            shield_decision=SHIELD_NOT_AUTHORIZED,
            simulated=True,
            reason=reason,
            created_at=now,
            updated_at=now,
        )
        new_position = None
        if filled > 0 and fill_price is not None:
            new_position = apply_fill(
                position,
                mint=instrument.mint,
                side=request.side,
                filled_quantity=filled,
                fill_price=fill_price,
                fee_quote=request.fee_quote,
                quote_symbol=instrument.quote_symbol,
                now=now,
            )
        return PaperCommit(order, events, new_position, instrument, False)

    def _result(
        self,
        request: PaperOrderRequest,
        instrument: SolanaInstrument,
        position: PositionRecord | None,
        now: datetime,
    ) -> tuple[Decimal, Decimal | None, str | None]:
        del now
        if request.outcome is SimulationOutcome.REJECT:
            return Decimal(0), None, "rejected"
        if request.outcome is SimulationOutcome.FAIL:
            return Decimal(0), None, "simulated_failure"
        price = _fill_price(request.side, request.reference_price, request.slippage_quote)
        require_scaled(price, instrument.price_decimals, "Fill price")
        filled = (
            request.quantity if request.outcome is SimulationOutcome.FILL else request.fill_quantity
        )
        if filled is None:
            raise TradingValidationError("A partial paper fill needs a fill quantity.")
        if request.side is OrderSide.SELL:
            available = Decimal(0) if position is None else position.quantity
            if filled > available:
                return Decimal(0), None, "insufficient_position"
        return filled, price, None


def refuse_live_execution(operation: str) -> None:
    """The only live entry point. It does not accept a payload and does not connect."""

    token = operation.strip()
    if not token or len(token) > 40 or not token.replace("_", "").isalpha():
        token = "unknown"
    raise TradingDisabled(
        f"Refusing {token}. Live execution is disabled. No wallet, signer, or swap will be called."
    )


def _fill_price(side: OrderSide, reference: Decimal, slippage: Decimal) -> Decimal:
    """Apply a supplied quote slippage. CYVORA does not calculate a pool impact."""

    price = reference + slippage if side is OrderSide.BUY else reference - slippage
    if price <= 0:
        raise TradingValidationError("The simulated fill price is not positive.")
    return price
