"""Register and route paper intents. A strategy cannot authorize itself."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import datetime

from domain.enums import ExecutionMode
from domain.exceptions import TradingDisabled, TradingValidationError
from domain.trading import OrderRecord, StrategyRecord, StrategyState
from trading.execution.gateway import PaperExecutionGateway, PaperOrderRequest
from trading.store import TradingStore

_STRATEGY_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
_SECRET_WORDS = ("private", "seed", "password", "api_key", "secret", "mnemonic")


class StrategyManager:
    """Lifecycle for named strategy slots.

    Starting and submitting require paper mode. The API startup path calls
    ``stop_running`` so a restart does not leave a strategy running.
    """

    def __init__(
        self,
        mode: ExecutionMode,
        store: TradingStore,
        gateway: PaperExecutionGateway,
        clock: Callable[[], datetime],
    ) -> None:
        self._mode = mode
        self._store = store
        self._gateway = gateway
        self._clock = clock

    def register(
        self,
        strategy_id: str,
        name: str,
        parameters: Mapping[str, str] | None = None,
    ) -> StrategyRecord:
        identifier = _require_strategy_id(strategy_id)
        label = name.strip()
        if not label or len(label) > 64:
            raise TradingValidationError("A strategy name must be 1 to 64 characters.")
        if self._store.get_strategy(identifier) is not None:
            raise TradingValidationError("That strategy id is already registered.")
        now = self._clock()
        record = StrategyRecord(
            strategy_id=identifier,
            name=label,
            state=StrategyState.REGISTERED,
            parameters=_parameters(parameters or {}),
            registered_at=now,
            updated_at=now,
        )
        return self._store.save_strategy(record)

    def start(self, strategy_id: str) -> StrategyRecord:
        self._require_paper()
        return self._set_state(strategy_id, StrategyState.RUNNING)

    def stop(self, strategy_id: str) -> StrategyRecord:
        return self._set_state(strategy_id, StrategyState.STOPPED)

    def stop_running(self) -> int:
        """Return every RUNNING strategy to STOPPED."""

        return self._store.stop_running_strategies(self._clock())

    def submit(self, strategy_id: str, request: PaperOrderRequest) -> OrderRecord:
        self._require_paper()
        identifier = _require_strategy_id(strategy_id)
        strategy = self._store.get_strategy(identifier)
        if strategy is None:
            raise TradingValidationError("That strategy is not registered.")
        if strategy.state is not StrategyState.RUNNING:
            raise TradingDisabled("A stopped strategy cannot submit a paper order.")
        if request.strategy_id != identifier:
            raise TradingValidationError("The order strategy does not match the route.")
        return self._gateway.submit(request)

    def _set_state(self, strategy_id: str, state: StrategyState) -> StrategyRecord:
        identifier = _require_strategy_id(strategy_id)
        current = self._store.get_strategy(identifier)
        if current is None:
            raise TradingValidationError("That strategy is not registered.")
        updated = StrategyRecord(
            strategy_id=current.strategy_id,
            name=current.name,
            state=state,
            parameters=current.parameters,
            registered_at=current.registered_at,
            updated_at=self._clock(),
        )
        return self._store.save_strategy(updated)

    def _require_paper(self) -> None:
        if self._mode is not ExecutionMode.PAPER:
            raise TradingDisabled(
                "Read-only mode does not start strategies or store simulated orders."
            )


def _require_strategy_id(value: str) -> str:
    identifier = value.strip()
    if _STRATEGY_ID.fullmatch(identifier) is None:
        raise TradingValidationError(
            "A strategy id must be 2 to 41 characters of lowercase letters, digits, _ or -."
        )
    return identifier


def _parameters(values: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    if len(values) > 20:
        raise TradingValidationError("A strategy can store at most 20 parameters.")
    cleaned: list[tuple[str, str]] = []
    for key, raw in values.items():
        name = key.strip()
        if not name or len(name) > 40 or not name.replace("_", "").isalnum():
            raise TradingValidationError("A parameter name must be 1 to 40 letters, digits, or _.")
        lowered = name.lower()
        if any(word in lowered for word in _SECRET_WORDS):
            raise TradingValidationError("Strategy parameters cannot be named like a secret.")
        if not isinstance(raw, str) or len(raw) > 80:
            raise TradingValidationError(
                "A parameter value must be a string of at most 80 characters."
            )
        cleaned.append((name, raw))
    return tuple(sorted(cleaned))
