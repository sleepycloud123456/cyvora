"""Interpreter and import checks for the Phase 1 foundation."""

from __future__ import annotations

import sys


def test_interpreter_is_python_313() -> None:
    assert sys.version_info[:2] == (3, 13)


def test_foundation_modules_import() -> None:
    import apps.api.main
    import apps.desktop.main
    import config.settings
    import database.connection
    import integrations.gmgn
    import monitoring.health

    assert callable(apps.api.main.create_app)
    assert callable(apps.desktop.main.main)
    assert config.settings.PHASE == "5"
    assert callable(integrations.gmgn.GMGNClient)
    assert callable(database.connection.check_database)
    assert callable(monitoring.health.collect_status)
