"""Alembic revision metadata can be listed without a database server."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_initial_revision_creates_application_metadata() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (
        root / "database" / "migrations" / "versions" / "20261110_0001_application_metadata.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0001_application_metadata"' in source
    assert "application_metadata" in source
    assert "placeholder" not in source.lower()


def test_alembic_heads_lists_the_radar_revision() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        check=False,
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert result.returncode == 0, result.stderr
    assert "0002_radar_intelligence" in result.stdout
    assert "postgresql" not in result.stdout.lower()
