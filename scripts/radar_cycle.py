"""Run one read-only radar cycle and print a redacted summary.

The process uses GMGN reads already allowed by the client. It does not print
the API key, the database URL, or a wallet key. Live trading stays off.
"""

from __future__ import annotations

import asyncio

from config.settings import get_settings
from database.repositories.radar import PostgresRadarRepository
from intelligence.cycle import run_radar_cycle


def main() -> None:
    """Store one cycle when the local key and database are configured."""

    settings = get_settings()
    if settings.gmgn_api_key is None:
        print("RADAR_CYCLE_FAIL reason=gmgn_not_configured")
        raise SystemExit(2)
    if not settings.database_url:
        print("RADAR_CYCLE_FAIL reason=database_not_configured")
        raise SystemExit(2)
    try:
        result = asyncio.run(run_radar_cycle(settings, PostgresRadarRepository(settings)))
    except Exception as exc:
        print(f"RADAR_CYCLE_FAIL error_type={type(exc).__name__}")
        raise SystemExit(1) from None
    print(result.public_report())
    if result.cycle_id is None or result.analysed_count == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
