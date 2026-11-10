"""Fail-closed execution gateway.

Phase 2 does not build a swap, a quote, an order query, or a signature.
"""

from __future__ import annotations

import re

from integrations.gmgn.errors import GMGNExecutionBlocked

_OPERATION = re.compile(r"[a-z_]{1,40}")


class GMGNExecutionGateway:
    """Reject every execution request without opening a socket."""

    def submit(self, operation: str, /, **payload: object) -> None:
        del payload
        name = operation if _OPERATION.fullmatch(operation) else "unknown"
        raise GMGNExecutionBlocked(
            f"Refusing {name}. Live execution is disabled and no GMGN trade route will be called."
        )
