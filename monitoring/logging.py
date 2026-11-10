"""Structured logging that does not record secrets."""

from __future__ import annotations

import logging

from config.settings import Settings
from monitoring.redaction import redact_text, secret_values

_LOGGER_NAME = "cyvora"


class RedactingFormatter(logging.Formatter):
    """Format a log record, then strip credentials from the finished line."""

    def __init__(self, secrets: tuple[str, ...] = ()) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
        self._secrets = secrets

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record), self._secrets)


def configure_logging(settings: Settings) -> logging.Logger:
    """Attach one stream handler and one file handler to the CYVORA logger.

    Existing handlers are closed first so repeated startup in tests does not
    leak file handles. The logger does not propagate to the root logger.
    """

    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(settings.log_level)
    logger.propagate = False
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)

    formatter = RedactingFormatter(secret_values(settings))
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    file_handler = logging.FileHandler(settings.log_dir / "cyvora.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger
