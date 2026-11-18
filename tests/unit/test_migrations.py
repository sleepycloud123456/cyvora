"""Alembic can list heads without a database server.

Upgrade, downgrade, paper orders, idempotency, and recovery run in
``tests/integration/test_postgres_regression.py`` against PostgreSQL 17.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_alembic_heads_lists_the_readiness_revision() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        check=False,
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert result.returncode == 0, result.stderr
    assert "0008_readiness" in result.stdout
    assert "postgresql" not in result.stdout.lower()
