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


def test_trading_revision_rejects_live_order_states() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (
        root / "database" / "migrations" / "versions" / "20261111_0003_trading_infrastructure.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0003_trading_infrastructure"' in source
    assert 'down_revision: str | None = "0002_radar_intelligence"' in source
    assert "ck_trading_orders_no_live_state" in source
    assert "ck_trading_orders_shield" in source


def test_alembic_heads_lists_the_trading_revision() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        check=False,
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert result.returncode == 0, result.stderr
    assert "0003_trading_infrastructure" in result.stdout
    assert "postgresql" not in result.stdout.lower()
