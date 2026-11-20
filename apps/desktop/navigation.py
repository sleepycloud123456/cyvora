"""Sidebar destinations for CYVORA Terminal.

`CATALOG` is the single list that restores a page: set `shown` to true and the
icon rail picks the page up in this order. Hidden entries keep their widgets.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NavItem:
    """One terminal destination."""

    name: str
    icon: str
    shown: bool = True


DASHBOARD = "Dashboard"
SYSTEM_HEALTH = "System Health"

CATALOG: tuple[NavItem, ...] = (
    NavItem(DASHBOARD, "dashboard"),
    NavItem("Open Positions", "positions"),
    NavItem("Trade History", "history"),
    NavItem("Paper Trading", "paper"),
    NavItem("Strategies", "strategies"),
    NavItem("Backtesting", "backtest"),
    NavItem("Risk Management", "shield"),
    NavItem("Analytics", "analytics"),
    NavItem("Notifications", "notifications"),
    NavItem(SYSTEM_HEALTH, "health"),
    NavItem("Live Scanner", "radar", shown=False),
    NavItem("Trending Tokens", "radar", shown=False),
    NavItem("New Launches", "radar", shown=False),
    NavItem("Token Analysis", "radar", shown=False),
    NavItem("Smart Money", "radar", shown=False),
    NavItem("Whale Tracker", "radar", shown=False),
    NavItem("Portfolio", "portfolio", shown=False),
    NavItem("CYVORA Intelligence", "analyst", shown=False),
    NavItem("Settings", "settings", shown=False),
)

PAGES: tuple[str, ...] = tuple(item.name for item in CATALOG if item.shown)
HIDDEN_PAGES: tuple[str, ...] = tuple(item.name for item in CATALOG if not item.shown)

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

IMPLEMENTED_PAGES = frozenset(item.name for item in CATALOG)
