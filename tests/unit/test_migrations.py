"""Alembic can list heads without a database server.

Upgrade, downgrade, paper orders, idempotency, and recovery run in
``tests/integration/test_postgres_regression.py`` against PostgreSQL 17.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_alembic_heads_lists_the_historical_pipeline() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        check=False,
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert result.returncode == 0, result.stderr
    assert "0009_historical_pipeline" in result.stdout
    assert "0008_readiness" not in result.stdout
    assert "postgresql" not in result.stdout.lower()
    source = (
        root / "database" / "migrations" / "versions" / "20261118_0009_historical_pipeline.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0009_historical_pipeline"' in source
    assert 'down_revision: str | None = "0008_readiness"' in source
    assert "live_trading_enabled IS false" in source
