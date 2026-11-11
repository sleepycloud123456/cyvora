"""Local explanations of stored evidence. This module does not call a model."""

from __future__ import annotations

from collections.abc import Mapping

from domain.shield import ShieldSnapshot
from domain.terminal import ADVISORY_NOTE, AnalystReport, AnalyticsView, Finding, PortfolioView
from intelligence.store import CycleSnapshot

_PROVIDER = "stored-evidence"
_MAX_TOKENS = 8


class StoredEvidenceAnalyst:
    """Explain rows CYVORA already stored. It has no network client."""

    name = _PROVIDER

    def explain(
        self,
        *,
        cycle: CycleSnapshot | None,
        shield: ShieldSnapshot,
        portfolio: PortfolioView,
        analytics: AnalyticsView,
    ) -> AnalystReport:
        findings: list[Finding] = []
        findings.extend(_tokens(cycle))
        findings.extend(_risk(shield))
        findings.append(_portfolio(portfolio))
        findings.extend(_strategies(analytics))
        if not findings:
            findings.append(
                Finding(
                    "coverage",
                    "No stored cycle, risk event, or paper result is available. "
                    "This is not a market conclusion.",
                    (),
                    None,
                    None,
                    ("stored evidence",),
                    False,
                )
            )
        return AnalystReport(
            provider=self.name,
            advisory=ADVISORY_NOTE,
            external_model_called=False,
            findings=tuple(findings),
            limitations=(
                "external_model_not_called",
                "advisory_only",
                "scores_do_not_authorize_entries",
            ),
        )


def explain_stored(
    *,
    cycle: CycleSnapshot | None,
    shield: ShieldSnapshot,
    portfolio: PortfolioView,
    analytics: AnalyticsView,
) -> AnalystReport:
    """Use the only implemented provider."""

    return StoredEvidenceAnalyst().explain(
        cycle=cycle, shield=shield, portfolio=portfolio, analytics=analytics
    )


def _tokens(cycle: CycleSnapshot | None) -> tuple[Finding, ...]:
    if cycle is None:
        return (
            Finding(
                "market",
                "No radar cycle is stored, so there is no market or token conclusion.",
                (),
                None,
                None,
                ("radar cycle",),
                False,
            ),
        )
    rows = []
    analyses = cycle.analyses[:_MAX_TOKENS]
    for detail in analyses:
        missing = [warning for warning in detail.warnings if "missing" in warning.lower()]
        if detail.score is None:
            missing.append("opportunity score")
        if detail.decision in {"UNKNOWN", "REJECTED"}:
            missing.append(f"decision {detail.decision}")
        confidence = detail.score
        indicator_names = ", ".join(name for name, _value in detail.indicators[:6]) or "none stored"
        summary = (
            f"{detail.symbol or detail.address} is {detail.decision}. {detail.explanation} "
            f"Stored indicators: {indicator_names}. "
            "Qualification for further analysis is not an entry."
        )
        rows.append(
            Finding(
                "token",
                summary,
                (
                    f"radar cycle {cycle.cycle_id}",
                    f"token {detail.address}",
                    f"security {detail.security_category}",
                    f"liquidity {detail.liquidity_status}",
                    f"smart money {detail.smart_money_status}",
                    f"whales {detail.whale_status}",
                ),
                cycle.finished_at,
                confidence,
                tuple(missing),
                False,
            )
        )
    if len(cycle.analyses) > _MAX_TOKENS:
        rows.append(
            Finding(
                "token",
                (
                    f"{len(cycle.analyses) - _MAX_TOKENS} additional stored analyses "
                    "are not expanded here."
                ),
                (f"radar cycle {cycle.cycle_id}",),
                cycle.finished_at,
                None,
                (),
                False,
            )
        )
    if not rows:
        rows.append(
            Finding(
                "market",
                "The stored cycle has no token analysis.",
                (f"radar cycle {cycle.cycle_id}",),
                cycle.finished_at,
                None,
                ("token analysis",),
                False,
            )
        )
    return tuple(rows)


def _risk(shield: ShieldSnapshot) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    if shield.breach_reasons or shield.halt_entries or shield.emergencies:
        triggers = sorted(
            {name for flag in shield.emergencies if flag.active for name in flag.triggers}
        )
        findings.append(
            Finding(
                "risk",
                "Shield posture is " + _posture(shield) + ". " + ADVISORY_NOTE,
                tuple(shield.breach_reasons) + tuple(triggers),
                None,
                None,
                () if shield.breach_reasons or triggers else ("breach reason",),
                False,
            )
        )
    return tuple(findings)


def _posture(shield: ShieldSnapshot) -> str:
    if shield.breach_latched:
        return "breached"
    if shield.halt_entries:
        return "entries paused"
    return "enforcing"


def _portfolio(portfolio: PortfolioView) -> Finding:
    missing: list[str] = []
    if portfolio.verified_equity is None:
        missing.append("verified paper equity")
    missing.append("wallet SOL balance")
    missing.append("USD value")
    if portfolio.unrealized is None and portfolio.open_positions:
        missing.append("unrealized result")
    summary = (
        f"Open paper positions: {portfolio.open_positions}. "
        f"Risk status: {portfolio.risk_status}. "
        f"{portfolio.verified_equity_detail} {portfolio.sol_balance_detail}"
    )
    return Finding("portfolio", summary, (), None, None, tuple(missing), False)


def _strategies(analytics: AnalyticsView) -> tuple[Finding, ...]:
    if not analytics.strategies and not analytics.research:
        return ()
    findings = []
    for strategy in analytics.strategies:
        findings.append(
            Finding(
                "strategy",
                f"Strategy {strategy.strategy_id} has {strategy.closed_trades} closed paper "
                "campaigns. "
                "No per-strategy equity curve is stored, so drawdown is not stated. "
                "The result is not deployed.",
                (strategy.strategy_id,),
                None,
                None,
                ("per-strategy drawdown",),
                False,
            )
        )
    for research in analytics.research:
        findings.append(
            Finding(
                "research",
                f"Simulation {research.run_id} ({research.kind}) records strategy "
                f"{research.strategy_id} on its own book. Parameters are not deployed.",
                (research.run_id, research.strategy_id),
                None,
                None,
                (),
                False,
            )
        )
    return tuple(findings)


def provider_names() -> Mapping[str, str]:
    """The configured provider map. Only the local provider exists."""

    return {_PROVIDER: "Explains stored CYVORA rows and does not call an external model."}
