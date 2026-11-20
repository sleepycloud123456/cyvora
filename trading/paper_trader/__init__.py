"""Autonomous paper trading. Orders go through the existing paper broker.

The broker is the same path the historical strategy runner uses: Shield,
idempotency, and PaperExecutionGateway. This package does not sign, call a
swap, or write a Nautilus fill into the CYVORA book.
"""

from domain.paper_trader import STRATEGY_ID

__all__ = ["STRATEGY_ID"]
