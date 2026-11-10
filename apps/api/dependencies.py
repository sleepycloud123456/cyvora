"""API dependencies."""

from __future__ import annotations

from fastapi import Request

from config.settings import Settings


def get_app_settings(request: Request) -> Settings:
    """Return the settings bound to this application instance."""

    settings: Settings = request.app.state.settings
    return settings
