"""Live-trading readiness records. These types cannot authorize a transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

NOT_AUTHORIZED = "not_authorized"
ENGAGE_CONFIRMATION = "ENGAGE"
RELEASE_CONFIRMATION = "RELEASE"


@dataclass(frozen=True, slots=True)
class ControlCheck:
    """One readiness control and whether the current code satisfies it."""

    name: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class GateDecision:
    """The live-trading gate. Phase 9 always leaves it closed."""

    authorized: bool
    live_trading_enabled: bool
    authorization_state: str
    reason: str
    checks: tuple[ControlCheck, ...]

    def public_mapping(self) -> dict[str, object]:
        return {
            "authorized": self.authorized,
            "live_trading_enabled": self.live_trading_enabled,
            "authorization_state": self.authorization_state,
            "reason": self.reason,
            "checks": [
                {"name": item.name, "status": item.status, "detail": item.detail}
                for item in self.checks
            ],
        }


@dataclass(frozen=True, slots=True)
class ReadinessEvent:
    """An operator control change. The confirmation word is not stored."""

    action: str
    result: str
    detail: str
    occurred_at: datetime
    live_trading_enabled: bool = False


@dataclass(frozen=True, slots=True)
class KillSwitchState:
    """The persisted operator latch. Live trading stays unauthorized."""

    engaged: bool
    authorization_state: str
    updated_at: datetime
    live_trading_enabled: bool = False

    def public_mapping(self) -> dict[str, object]:
        return {
            "engaged": self.engaged,
            "authorization_state": self.authorization_state,
            "updated_at": self.updated_at.isoformat(),
            "live_trading_enabled": self.live_trading_enabled,
        }
