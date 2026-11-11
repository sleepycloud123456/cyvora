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


def test_shield_revision_keeps_live_trading_off() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (
        root / "database" / "migrations" / "versions" / "20261111_0004_shield_risk_engine.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0004_shield_risk_engine"' in source
    assert 'down_revision: str | None = "0003_trading_infrastructure"' in source
    assert "ck_shield_decisions_live" in source
    assert "paper_approved" in source
    assert "live_approved" not in source


def test_simulation_revision_keeps_parameters_undeployed() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (
        root / "database" / "migrations" / "versions" / "20261111_0005_simulation.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0005_simulation"' in source
    assert 'down_revision: str | None = "0004_shield_risk_engine"' in source
    assert "ck_simulation_runs_deploy" in source
    assert "ck_simulation_runs_live" in source
    assert "parameters_deployed IS false" in source


def test_terminal_revision_keeps_live_trading_and_telegram_off() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (
        root / "database" / "migrations" / "versions" / "20261111_0006_terminal.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0006_terminal"' in source
    assert 'down_revision: str | None = "0005_simulation"' in source
    assert "ck_terminal_profiles_live" in source
    assert "ck_terminal_preferences_telegram" in source
    assert "ck_terminal_notifications_live" in source
    assert "live_trading_enabled IS false" in source
    assert "telegram_delivery IS false" in source


def test_operations_revision_keeps_wallet_and_cloud_locked() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (
        root / "database" / "migrations" / "versions" / "20261111_0007_operations.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0007_operations"' in source
    assert 'down_revision: str | None = "0006_terminal"' in source
    assert "ck_operation_recoveries_wallet" in source
    assert "ck_operation_recoveries_flat" in source
    assert "ck_operation_workers_cloud" in source
    assert "ck_operation_workers_live" in source
    assert "auth_events" in source
    assert "token" not in source.lower()


def test_readiness_revision_keeps_live_trading_unauthorized() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (
        root / "database" / "migrations" / "versions" / "20261111_0008_readiness.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0008_readiness"' in source
    assert 'down_revision: str | None = "0007_operations"' in source
    assert "ck_readiness_controls_live" in source
    assert "ck_readiness_controls_authorization" in source
    assert "not_authorized" in source
    assert "live_authorized" not in source


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
    assert "0008_readiness" in result.stdout
    assert "postgresql" not in result.stdout.lower()
