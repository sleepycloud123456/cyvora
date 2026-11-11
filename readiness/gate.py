"""The live-trading gate. A satisfied checklist does not open it."""

from __future__ import annotations

from domain.readiness import NOT_AUTHORIZED, ControlCheck, GateDecision

_CLOSED = (
    "Live trading is not authorized. Phase 9 records readiness and does not grant it. "
    "A separate explicit authorization from the operator is required, and this process "
    "has no control that can record one."
)


def standard_checks() -> tuple[ControlCheck, ...]:
    """Describe the controls that exist today. Absent chain controls stay absent."""

    return (
        ControlCheck(
            "wallet_compatibility",
            "absent",
            "No wallet is bound. GMGN_PRIVATE_KEY is not loaded. "
            "Holdings and wallet activity stay refused.",
        ),
        ControlCheck(
            "execution_permissions",
            "present",
            "READ_ONLY and PAPER are the only modes. LIVE, LIVE_LOCKED, and "
            "LIVE_AUTHORIZED are rejected. The execution gateway raises before any socket.",
        ),
        ControlCheck(
            "risk_enforcement",
            "partial",
            "Shield approves or denies every new paper order. A paper approval cannot "
            "submit a live order. Chain spending is not enforced because no wallet is read.",
        ),
        ControlCheck(
            "transaction_simulation",
            "partial",
            "Paper orders pass through a local simulator. There is no Solana transaction "
            "simulation and no RPC client.",
        ),
        ControlCheck(
            "transaction_confirmation",
            "partial",
            "A paper CONFIRMED state is a simulator result. It is not a chain confirmation.",
        ),
        ControlCheck(
            "reconciliation",
            "partial",
            "The paper book is reconciled from stored orders and positions. "
            "Wallet reconciliation stays not_authorized, and a missing wallet is not flat.",
        ),
        ControlCheck(
            "duplicate_prevention",
            "partial",
            "A repeated paper idempotency key returns the stored order and does not fill again. "
            "That rule is not a chain-transaction deduplication.",
        ),
        ControlCheck(
            "emergency_controls",
            "present",
            "The operator kill switch blocks new operator paper orders. It does not flatten "
            "a position, sign, or submit. Resume and the analyst cannot release it.",
        ),
        ControlCheck(
            "failure_recovery",
            "partial",
            "Startup recovery reads the stored paper book and blocks new paper API entries "
            "when that book is inconsistent or unreadable. It does not read a wallet.",
        ),
        ControlCheck(
            "api_disconnection",
            "partial",
            "GMGN transport failures are recorded and retries stay bounded. No live order "
            "can be left in flight because live submission is refused.",
        ),
        ControlCheck(
            "balance_verification",
            "absent",
            "Wallet SOL and token balances are not read. Verified equity is the last "
            "Shield baseline, not a chain balance.",
        ),
        ControlCheck(
            "spending_limits",
            "partial",
            "Shield enforces paper allocation, loss, and liquidity limits. "
            "There is no on-chain spending limit.",
        ),
        ControlCheck(
            "audit_trails",
            "present",
            "Paper orders, Shield decisions, authentication results, and kill-switch "
            "changes are stored. Secret values are not stored.",
        ),
    )


def live_gate(checks: tuple[ControlCheck, ...] | None = None) -> GateDecision:
    """Return a closed gate.

    The caller cannot pass an authorization flag. Supplying checks that are all
    marked present still leaves the gate closed.
    """

    return GateDecision(
        authorized=False,
        live_trading_enabled=False,
        authorization_state=NOT_AUTHORIZED,
        reason=_CLOSED,
        checks=standard_checks() if checks is None else checks,
    )
