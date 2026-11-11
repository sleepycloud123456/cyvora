"""Expected CYVORA failures."""

from __future__ import annotations


class CyvoraError(Exception):
    """Base type for errors the application knows how to classify."""


class ConfigurationError(CyvoraError):
    """The process was given settings it must not start with."""


class DatabaseNotConfiguredError(CyvoraError):
    """A database operation was requested without CYVORA_DATABASE_URL."""


class DatabaseUnavailableError(CyvoraError):
    """PostgreSQL was configured but could not be reached."""


class RadarNotConfigured(CyvoraError):
    """A radar cycle was requested without the database or the GMGN key."""
