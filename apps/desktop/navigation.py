"""Sidebar destinations for CYVORA Terminal."""

from __future__ import annotations

DASHBOARD = "Dashboard"
SYSTEM_HEALTH = "System Health"

PAGES: tuple[str, ...] = (
    DASHBOARD,
    "Live Scanner",
    "Trending Tokens",
    "New Launches",
    "Token Analysis",
    "Smart Money",
    "Whale Tracker",
    "Open Positions",
    "Trade History",
    "Strategies",
    "Risk Management",
    "Portfolio",
    "Backtesting",
    "Paper Trading",
    "Analytics",
    "CYVORA Intelligence",
    "Notifications",
    "Settings",
    SYSTEM_HEALTH,
)

IMPLEMENTED_PAGES = frozenset({DASHBOARD, SYSTEM_HEALTH})
