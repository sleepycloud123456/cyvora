"""Interpreter and import checks for the Phase 1 foundation."""

from __future__ import annotations

import sys
from importlib.metadata import version


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
    assert config.settings.PHASE == "9"
    assert callable(integrations.gmgn.GMGNClient)
    assert callable(database.connection.check_database)
    assert callable(monitoring.health.collect_status)


def test_patched_fsspec_imports_beside_nautilus() -> None:
    """PYSEC-2026-4217 is fixed in fsspec 2026.6.0. Nautilus stays 1.231.0."""

    installed = version("fsspec")
    parts = tuple(int(piece) for piece in installed.split(".")[:3])
    assert parts >= (2026, 6, 0)
    assert version("nautilus-trader") == "1.231.0"
    import fsspec
    import nautilus_trader

    filesystem = fsspec.filesystem("file")
    assert filesystem.exists(__file__)
    assert nautilus_trader.__name__ == "nautilus_trader"
