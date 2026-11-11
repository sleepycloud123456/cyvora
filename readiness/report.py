"""The Phase 9 readiness report. It does not claim that live trading is safe."""

from __future__ import annotations

import json

from config.settings import APP_NAME, APP_VERSION, PHASE, Settings
from domain.readiness import GateDecision
from readiness.gate import live_gate
from readiness.guard import kill_switch_component

# Decisions the operator must make before any later phase may even be asked
# to consider live trading. None of these are granted by this report.
OPERATOR_DECISIONS: tuple[str, ...] = (
    "Give a separate explicit authorization to enable live trading after reading "
    "the readiness report. That authorization has not been given, and this phase "
    "cannot record it.",
    "Choose a wallet path and say whether CYVORA may ever load a signing key. "
    "Today no key is loaded, and adding GMGN_PRIVATE_KEY is not authorized.",
    "Choose a Solana RPC provider, accept its cost and trust terms, and say which "
    "reads are allowed. No RPC client is included.",
    "Set real spending limits, a SOL fee reserve, and the maximum loss that must "
    "stop new entries. Shield's paper limits are not those chain limits.",
    "Decide whether a kill switch must also cancel an in-flight transaction. "
    "The current switch only refuses new operator paper orders. It cannot cancel "
    "a chain transaction because none are submitted.",
    "Decide who may release the kill switch. Today the desktop operator, or a "
    "caller that already has the local API token, can release it with the "
    "confirmation word. The word is an interlock, not a second secret.",
    "Decide whether the public GitHub repository should stay public before any "
    "live-trading notes, host details, or operational records are added.",
    "Accept that paper fills, radar scores, and analyst findings do not predict "
    "a live fill and cannot authorize one.",
    "Authorize any paid GMGN plan, Telegram bot, Windows service, or cloud host "
    "separately. None of those is turned on by this phase.",
    "Keep the API on loopback, or commission a separate security design before "
    "any non-loopback bind. This phase does not add that design.",
)


def build_report(settings: Settings | None = None) -> dict[str, object]:
    """Return the public readiness report. Secrets are not fields."""

    decision: GateDecision = live_gate()
    kill_state = "not_configured"
    if settings is not None:
        kill_state = kill_switch_component(settings).state
    return {
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "phase": PHASE,
        "live_trading_enabled": False,
        "authorization_state": decision.authorization_state,
        "ready_for_live": False,
        "kill_switch": kill_state,
        "gate": decision.public_mapping(),
        "operator_decisions": list(OPERATOR_DECISIONS),
        "isolated_backtests": (
            "An isolated research ledger does not consult the kill switch. "
            "It does not write the operator paper book and it does not sign."
        ),
    }


def main() -> None:
    """Print the readiness report. The environment is not included."""

    from config.settings import assert_runtime_safe, get_settings

    settings = get_settings()
    assert_runtime_safe(settings)
    print(json.dumps(build_report(settings), indent=2, sort_keys=True))
    print("live_trading_enabled=false")


if __name__ == "__main__":
    main()
