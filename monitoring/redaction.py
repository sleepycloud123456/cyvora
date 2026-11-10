"""Redact credentials before they can reach a log line or a report."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from config.settings import Settings

_ASSIGNMENT = re.compile(
    r"(?i)\b((?:GMGN_API_KEY|CYVORA_GMGN_API_KEY|GMGN_PRIVATE_KEY|X-APIKEY|"
    r"AUTHORIZATION)\s*[=:]\s*(?:bearer\s+)?)(\S+)"
)
_DATABASE_URL = re.compile(r"(?i)(postgresql(?:\+psycopg)?://[^:\s']+:)([^@\s']+)(@)")
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_MIN_SECRET_LENGTH = 8


def secret_values(settings: Settings) -> tuple[str, ...]:
    """Return configured secret strings that logs must not contain.

    Values shorter than eight characters are omitted. Replacing those would
    also rewrite ordinary words.
    """

    found: list[str] = []
    if settings.gmgn_api_key is not None:
        key = settings.gmgn_api_key.get_secret_value()
        if len(key) >= _MIN_SECRET_LENGTH:
            found.append(key)
    if settings.database_url:
        try:
            password = urlsplit(settings.database_url).password
        except ValueError:
            password = None
        if password and len(password) >= _MIN_SECRET_LENGTH:
            found.append(password)
    return tuple(found)


def redact_text(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Remove known secrets and credential-shaped text."""

    redacted = text
    for secret in secrets:
        if len(secret) >= _MIN_SECRET_LENGTH and secret in redacted:
            redacted = redacted.replace(secret, "***")
    redacted = _PRIVATE_KEY_BLOCK.sub("***", redacted)
    redacted = _ASSIGNMENT.sub(r"\1***", redacted)
    return _DATABASE_URL.sub(r"\1***\3", redacted)
