"""Alembic can list heads without a database server.

Upgrade, downgrade, paper orders, idempotency, and recovery run in
``tests/integration/test_postgres_regression.py`` against PostgreSQL 17.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_alembic_heads_lists_one_paper_trader_head() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        check=False,
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert result.returncode == 0, result.stderr
    heads = [line.strip() for line in result.stdout.splitlines() if "(head)" in line]
    assert heads == ["0012_paper_trader_exited (head)"]
    assert "postgresql" not in result.stdout.lower()
    historical = (
        root / "database" / "migrations" / "versions" / "20261118_0009_historical_pipeline.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0009_historical_pipeline"' in historical
    assert 'down_revision: str | None = "0008_readiness"' in historical
    assert "live_trading_enabled IS false" in historical
    trader = (
        root / "database" / "migrations" / "versions" / "20261119_0010_paper_trader.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0010_paper_trader"' in trader
    assert 'down_revision: str | None = "0009_historical_pipeline"' in trader
    kinds = (
        root / "database" / "migrations" / "versions" / "20261119_0011_worker_kinds.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str | None = "0010_paper_trader"' in kinds
    exited = (
        root / "database" / "migrations" / "versions" / "20261120_0012_paper_trader_exited.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0012_paper_trader_exited"' in exited
    assert 'down_revision: str | None = "0011_worker_kinds"' in exited
    assert "LIVE" not in exited
    assert "live_trading_enabled IS false" in trader
