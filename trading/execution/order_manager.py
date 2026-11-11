"""Paper order states. Chain submission states are rejected here."""

from __future__ import annotations

from domain.exceptions import TradingDisabled
from domain.trading import LIVE_ORDER_STATES, OrderState, SimulationOutcome

_FILL_PATH = (
    OrderState.CREATED,
    OrderState.VALIDATED,
    OrderState.SIMULATION_PENDING,
    OrderState.SIMULATION_PASSED,
    OrderState.CONFIRMED,
)
_FAILURE_PATH = (
    OrderState.CREATED,
    OrderState.VALIDATED,
    OrderState.SIMULATION_PENDING,
    OrderState.FAILED,
)


def ensure_paper_state(state: OrderState) -> None:
    """Refuse the states that would mean a transaction was sent."""

    if state in LIVE_ORDER_STATES:
        raise TradingDisabled(
            "Paper execution cannot enter a submission or chain-confirmation state."
        )


def paper_states(outcome: SimulationOutcome) -> tuple[OrderState, ...]:
    """Return the only transitions a paper order may record."""

    path: tuple[OrderState, ...]
    if outcome in {SimulationOutcome.FILL, SimulationOutcome.PARTIAL}:
        path = _FILL_PATH
    else:
        path = _FAILURE_PATH
    for state in path:
        ensure_paper_state(state)
    return path


def paper_denied_states() -> tuple[OrderState, ...]:
    """States for an order Shield refused before the simulator ran."""

    path = (OrderState.CREATED, OrderState.VALIDATED, OrderState.FAILED)
    for state in path:
        ensure_paper_state(state)
    return path
