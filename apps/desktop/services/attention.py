"""Plain-language status for an unreachable API or stale stored data."""

from __future__ import annotations

from domain.status import StatusSnapshot


def attention_text(snapshot: StatusSnapshot) -> str:
    """Return a banner sentence, or an empty string when nothing needs one."""

    lines: list[str] = []
    if snapshot.backend.state == "offline":
        lines.append(
            "API is down. CYVORA Terminal cannot reach the loopback API. "
            "Stored rows on screen can be stale. This window does not start the API."
        )
    elif snapshot.backend.state == "degraded":
        lines.append(
            "The API is degraded. Stored rows on screen can be stale. "
            "This window does not start the API."
        )
    if snapshot.market_data.state == "stale":
        lines.append(
            "Stored market data is stale. The latest radar cycle is older than "
            "the freshness window. These figures are not live prices."
        )
    return " ".join(lines)
