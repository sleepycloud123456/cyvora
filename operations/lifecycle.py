"""Record a local process start or stop. The detail is a fixed sentence."""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from config.settings import Settings
from database.connection import create_database_engine
from database.models.operations import OperationLifecycle

logger = logging.getLogger("cyvora.operations")

_COMPONENTS = frozenset({"api", "supervisor", "desktop", "launcher"})
_ACTIONS = frozenset({"started", "stopped"})
_DETAILS = {
    ("api", "started"): "The API process is serving.",
    ("api", "stopped"): "The API process stopped.",
    ("supervisor", "started"): "The supervisor process started.",
    ("supervisor", "stopped"): "The supervisor process stopped.",
    ("desktop", "started"): "The desktop process started.",
    ("desktop", "stopped"): "The desktop process stopped.",
    ("launcher", "started"): "The launcher started the local processes.",
    ("launcher", "stopped"): "The launcher stopped the local processes.",
}


def record_lifecycle(
    settings: Settings,
    component: str,
    action: str,
    *,
    now: datetime | None = None,
) -> bool:
    """Insert one lifecycle row. A missing database or a driver error is not raised."""

    if component not in _COMPONENTS or action not in _ACTIONS:
        return False
    if not settings.database_url:
        return False
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    engine = create_database_engine(settings)
    try:
        with Session(engine) as session:
            session.add(
                OperationLifecycle(
                    component=component,
                    action=action,
                    detail=_DETAILS[(component, action)],
                    occurred_at=moment,
                    live_trading_enabled=False,
                )
            )
            session.commit()
    except Exception as exc:
        logger.warning("lifecycle record failed error_type=%s", type(exc).__name__)
        return False
    finally:
        engine.dispose()
    return True


def main(argv: list[str] | None = None) -> None:
    """Record one launcher event. The command does not print a database URL."""

    from config.settings import assert_runtime_safe, get_settings

    parser = argparse.ArgumentParser(prog="cyvora-lifecycle")
    parser.add_argument("--component", required=True, choices=sorted(_COMPONENTS))
    parser.add_argument("--action", required=True, choices=sorted(_ACTIONS))
    args = parser.parse_args(argv)
    settings = get_settings()
    assert_runtime_safe(settings)
    if not settings.database_url:
        print("CYVORA_LIFECYCLE_SKIP reason=not_configured")
        print("live_trading_enabled=false")
        raise SystemExit(0)
    saved = record_lifecycle(settings, args.component, args.action)
    if not saved:
        print("CYVORA_LIFECYCLE_FAIL reason=record")
        print("live_trading_enabled=false")
        raise SystemExit(1)
    print("CYVORA_LIFECYCLE_OK")
    print(f"component={args.component}")
    print(f"action={args.action}")
    print("live_trading_enabled=false")


if __name__ == "__main__":
    main()
