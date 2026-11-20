"""Launcher checks that print a status word and not a connection string."""

from __future__ import annotations

from config.settings import assert_runtime_safe, get_settings
from database.connection import check_database
from operations.backup import _target


def main() -> None:
    """Report whether the configured database is a reachable loopback server."""

    settings = get_settings()
    assert_runtime_safe(settings)
    if not settings.database_url:
        print("CYVORA_POSTGRES_FAIL reason=not_configured")
        print("live_trading_enabled=false")
        raise SystemExit(2)
    if _target(settings.database_url) is None:
        print("CYVORA_POSTGRES_FAIL reason=refused")
        print("live_trading_enabled=false")
        raise SystemExit(2)
    status = check_database(settings)
    if status.state != "reachable":
        print(f"CYVORA_POSTGRES_FAIL reason={status.state}")
        print("live_trading_enabled=false")
        raise SystemExit(2)
    print("CYVORA_POSTGRES_OK")
    print("live_trading_enabled=false")


if __name__ == "__main__":
    main()
