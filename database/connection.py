"""PostgreSQL connectivity for local development."""

from __future__ import annotations

import logging
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from config.settings import Settings
from domain.exceptions import DatabaseNotConfiguredError
from domain.status import ComponentStatus

logger = logging.getLogger("cyvora.database")


def redact_database_url(url: str) -> str:
    """Return a database URL with any password removed.

    If the URL cannot be parsed, return a fixed redacted marker rather than
    the original text.
    """

    try:
        parts = urlsplit(url)
    except ValueError:
        return "postgresql://***"
    if parts.password is None and "@" not in (parts.netloc or ""):
        return url
    username = parts.username or ""
    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port is not None else ""
    userinfo = f"{username}:***" if username else "***"
    netloc = f"{userinfo}@{hostname}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def create_database_engine(settings: Settings) -> Engine:
    """Open a short-lived engine. Caller must dispose it."""

    if not settings.database_url:
        raise DatabaseNotConfiguredError(
            "CYVORA_DATABASE_URL is not set. Refusing to assume a database."
        )
    return create_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 3},
    )


def check_database(settings: Settings) -> ComponentStatus:
    """Report whether the configured local PostgreSQL server can be reached.

    Driver exception text is not returned. Those messages can contain the URL.
    """

    if not settings.database_url:
        return ComponentStatus(
            state="not_configured",
            detail="CYVORA_DATABASE_URL is not set. PostgreSQL has not been contacted.",
        )
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("database check failed error_type=%s", type(exc).__name__)
        return ComponentStatus(
            state="unreachable",
            detail=(
                "PostgreSQL could not be reached. The driver message was withheld "
                "because it can contain the database URL."
            ),
        )
    else:
        return ComponentStatus(
            state="reachable",
            detail="PostgreSQL accepted a connection.",
        )
    finally:
        engine.dispose()
