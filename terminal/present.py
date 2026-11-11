"""Text and JSON for the terminal. Decimals stay strings. Secrets are not included."""

from __future__ import annotations

from decimal import Decimal

from domain.terminal import (
    AnalystReport,
    AnalyticsView,
    PortfolioView,
    TerminalSnapshot,
)
from intelligence.numbers import format_decimal


def money(value: Decimal | None) -> str:
    if value is None:
        return "none"
    return format_decimal(value) or "none"


def portfolio_text(view: PortfolioView) -> str:
    """Operator-facing portfolio summary. Missing figures stay missing."""

    return "\n".join(
        (
            view.verified_equity_detail,
            f"Verified equity: {money(view.verified_equity)}.",
            view.sol_balance_detail,
            view.usd_detail,
            f"Allocated cost: {money(view.allocated)} {view.allocated_unit or ''}".rstrip(),
            view.allocated_detail,
            f"Available: {money(view.available)}. {view.available_detail}",
            f"Open positions: {view.open_positions}.",
            f"Unrealized: {money(view.unrealized)}. {view.unrealized_detail}",
            f"Realized: {money(view.realized)} {view.realized_unit or ''}. {view.realized_detail}",
            f"Daily PnL: {money(view.daily_pnl)}. {view.daily_pnl_detail}",
            f"Total: {money(view.total_pnl)}. {view.total_pnl_detail}",
            f"Win rate: {money(view.win_rate)}. {view.win_rate_detail}",
            f"Average closed result: {money(view.average_profit)}. {view.average_profit_detail}",
            f"Active strategies: {view.active_strategies}.",
            f"Market condition: {view.market_condition}. {view.market_detail}",
            f"Risk: {view.risk_status}. {view.risk_detail}",
            f"Exposure: {money(view.exposure)}. {view.exposure_detail}",
            f"Drawdown: {money(view.max_drawdown)}. {view.drawdown_detail}",
            f"SOL reserve fraction: {money(view.sol_reserve_fraction)}. {view.sol_reserve_detail}",
            "Recent paper orders:",
            *(_order_line(view) or ("No simulated orders are stored.",)),
        )
    )


def analytics_text(view: AnalyticsView) -> str:
    lines = [
        f"Stored equity points: {len(view.equity_points)}.",
        f"Verified-equity change: {money(view.net_profit)}.",
        f"Fees on filled paper orders: {money(view.fees)}.",
        f"Closed campaigns: {view.wins} wins, {view.losses} losses, {view.flats} flat.",
        f"Average holding seconds: {money(view.average_holding_seconds)}. {view.holding_detail}",
        "Sharpe: "
        + money(view.sharpe)
        + ". "
        + (view.sharpe_reason or "computed from stored equity changes")
        + ".",
        "Sortino: "
        + money(view.sortino)
        + ". "
        + (view.sortino_reason or "computed from stored equity changes")
        + ".",
        f"Risk-adjusted: {money(view.risk_adjusted)}.",
        "Limitations: " + (", ".join(view.limitations) or "none"),
        "Strategy results are closed paper campaigns. No per-strategy drawdown is stored.",
    ]
    if not view.strategies:
        lines.append("No closed paper campaign is stored.")
    for strategy in view.strategies:
        lines.append(
            f"{strategy.strategy_id}: trades {strategy.closed_trades}, "
            f"net {money(strategy.net_pnl)}, win rate {money(strategy.win_rate)}, "
            f"profit factor {money(strategy.profit_factor)}."
        )
    lines.append("Token results:")
    if not view.tokens:
        lines.append("No closed token result is stored.")
    for token in view.tokens:
        lines.append(f"{token.mint}: trades {token.trades}, net {money(token.net_pnl)}.")
    lines.append("Research comparisons are separate simulation books. Parameters are not deployed.")
    if not view.research:
        lines.append("No simulation report is stored.")
    for research in view.research:
        lines.append(
            f"{research.run_id} {research.kind} {research.strategy_id}: "
            f"net {money(research.net_profit)}, trades {research.trade_count}, "
            f"drawdown {money(research.max_drawdown)}, deployed {research.parameters_deployed}."
        )
    lines.append("Daily changes:")
    if not view.daily:
        lines.append("Fewer than two equity baselines are stored.")
    for change in view.daily:
        lines.append(f"{change.session_date.isoformat()}: {money(change.value)}. {change.detail}")
    lines.append("Weekly sums of those stored changes:")
    for period in view.weekly:
        lines.append(f"{period.label}: {money(period.value)}.")
    lines.append("Monthly sums of those stored changes:")
    for period in view.monthly:
        lines.append(f"{period.label}: {money(period.value)}.")
    return "\n".join(lines)


def analyst_text(report: AnalystReport) -> str:
    lines = [
        f"Provider: {report.provider}.",
        report.advisory,
        "External model called: no."
        if not report.external_model_called
        else "External model called: yes.",
        "Limitations: " + ", ".join(report.limitations),
    ]
    for finding in report.findings:
        lines.append("")
        lines.append(f"{finding.topic}: {finding.summary}")
        if finding.observed_at:
            lines.append(f"Observed at: {finding.observed_at}.")
        if finding.confidence is not None:
            lines.append(f"Stored confidence or score: {finding.confidence}.")
        else:
            lines.append("Stored confidence: missing.")
        if finding.evidence:
            lines.append("Evidence: " + "; ".join(finding.evidence) + ".")
        if finding.missing:
            lines.append("Missing: " + "; ".join(finding.missing) + ".")
        lines.append("Authorizes an order: no.")
    return "\n".join(lines)


def strategy_text(view: AnalyticsView) -> str:
    if not view.strategies:
        return (
            "No closed paper campaign is stored for a strategy. "
            "Starting a strategy does not submit an order."
        )
    return analytics_text(view).split("Token results:")[0].strip()


def snapshot_payload(snapshot: TerminalSnapshot) -> dict[str, object]:
    """Public JSON. Live trading, Telegram, and analyst authority stay false."""

    portfolio = snapshot.portfolio
    return {
        "generated_at": snapshot.generated_at.isoformat(),
        "live_trading_enabled": False,
        "live_control_present": False,
        "telegram_delivery": False,
        "external_model_called": snapshot.analyst.external_model_called,
        "authorizes_order": False,
        "execution_mode": snapshot.settings.execution_mode,
        "manual_override_locked": True,
        "paper_orders_allowed": snapshot.settings.paper_orders_allowed,
        "database_configured": snapshot.settings.database_configured,
        "gmgn_configured": snapshot.settings.gmgn_configured,
        "api_host": snapshot.settings.api_host,
        "api_port": snapshot.settings.api_port,
        "halt_entries": snapshot.settings.halt_entries,
        "breach_latched": snapshot.settings.breach_latched,
        "active_profile_id": snapshot.active_profile_id,
        "profiles": [
            {
                "profile_id": item.profile_id,
                "name": item.name,
                "strategy_ids": list(item.strategy_ids),
                "signal_threshold": item.signal_threshold,
                "signal_threshold_applied": False,
                "active": item.active,
                "live_trading_enabled": False,
                "authority_note": item.authority_note,
            }
            for item in snapshot.profiles
        ],
        "preferences": {
            "enabled_categories": list(snapshot.preferences.enabled_categories),
            "quiet_start_minute": snapshot.preferences.quiet_start_minute,
            "quiet_end_minute": snapshot.preferences.quiet_end_minute,
            "minimum_repeat_seconds": snapshot.preferences.minimum_repeat_seconds,
            "telegram_delivery": False,
            "live_trading_enabled": False,
        },
        "portfolio": {
            "verified_equity": money(portfolio.verified_equity),
            "verified_equity_detail": portfolio.verified_equity_detail,
            "sol_balance_detail": portfolio.sol_balance_detail,
            "usd_detail": portfolio.usd_detail,
            "open_positions": portfolio.open_positions,
            "risk_status": portfolio.risk_status,
            "win_rate": money(portfolio.win_rate),
        },
        "notifications": [
            {
                "category": item.category,
                "subject": item.subject,
                "detail": item.detail,
                "evidence_at": item.evidence_at.isoformat(),
                "withheld": item.withheld,
                "delivered_telegram": False,
            }
            for item in snapshot.notifications
        ],
        "analyst_limitations": list(snapshot.analyst.limitations),
        "findings": [
            {
                "topic": item.topic,
                "summary": item.summary,
                "authorizes_order": False,
                "missing": list(item.missing),
            }
            for item in snapshot.analyst.findings
        ],
    }


def _order_line(view: PortfolioView) -> tuple[str, ...]:
    return tuple(
        (
            f"{item.updated_at.isoformat()} {item.symbol} {item.side} "
            f"{item.state} {item.shield_decision}"
        )
        for item in view.recent
    )
