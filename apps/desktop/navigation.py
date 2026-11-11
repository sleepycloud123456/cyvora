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

RADAR_MODES = {
    "Live Scanner": "rankings",
    "Trending Tokens": "trending",
    "New Launches": "launches",
    "Token Analysis": "analysis",
    "Smart Money": "smart",
    "Whale Tracker": "whales",
}

TRADING_PAGES = {
    "Open Positions": "positions",
    "Trade History": "orders",
    "Strategies": "strategies",
}

SIMULATION_PAGES = frozenset({"Backtesting", "Paper Trading"})

TERMINAL_PAGES = frozenset(
    {
        "Portfolio",
        "Analytics",
        "CYVORA Intelligence",
        "Notifications",
        "Settings",
    }
)

IMPLEMENTED_PAGES = frozenset(PAGES)
