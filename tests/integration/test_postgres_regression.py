"""PostgreSQL 17 checks for migrations, paper orders, idempotency, and recovery.

Set ``CYVORA_TEST_DATABASE_URL`` to a disposable database. The tests drop and
recreate schema ``public`` on that database. They do not read ``.env``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from config.settings import Settings
from database.repositories.trading import PostgresTradingRepository
from domain.enums import ExecutionMode
from domain.exceptions import TradingDisabled
from domain.operations import WALLET_NOT_AUTHORIZED
from domain.shield import PAPER_APPROVED, ExitKind, RiskIntent
from domain.trading import OrderSide, OrderState, SimulationOutcome, SolanaInstrument
from operations.recovery import startup_recovery
from trading.execution.gateway import PaperExecutionGateway, PaperOrderRequest

ROOT = Path(__file__).resolve().parents[2]
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
NOW = datetime(2026, 11, 18, tzinfo=UTC)
_BOOK_TABLES = (
    "trading_order_events",
    "trading_reconciliations",
    "trading_orders",
    "trading_positions",
    "trading_instruments",
    "trading_strategies",
    "shield_decisions",
    "shield_notices",
    "shield_emergencies",
    "shield_stops",
    "shield_campaigns",
    "shield_daily",
    "shield_controls",
    "operation_recoveries",
)


def _test_database_url() -> str | None:
    value = os.environ.get("CYVORA_TEST_DATABASE_URL", "").strip()
    if not value:
        return None
    if not value.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail("CYVORA_TEST_DATABASE_URL must be a postgresql URL.")
    return value


class _Database:
    """Disposable PostgreSQL URL. The repr omits the password."""

    def __init__(self, url: str) -> None:
        self.url = url

    def __repr__(self) -> str:
        return "_Database(postgresql://***)"


def _engine(database: _Database) -> Engine:
    return create_engine(database.url, poolclass=NullPool, connect_args={"connect_timeout": 10})


def _redact(detail: str, url: str) -> str:
    return detail.replace(url, "postgresql://***")


def _run_alembic(database: _Database, *args: str) -> None:
    env = os.environ.copy()
    env["CYVORA_DATABASE_URL"] = database.url
    env.pop("GMGN_PRIVATE_KEY", None)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = _redact(result.stderr or result.stdout, database.url)
        raise AssertionError(f"alembic {' '.join(args)} failed.\n{detail}")


def _reset_public(database: _Database) -> None:
    engine = _engine(database)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    except Exception as exc:
        raise AssertionError(f"PostgreSQL schema reset failed with {type(exc).__name__}.") from None
    finally:
        engine.dispose()


def _scalar(database: _Database, statement: str) -> object:
    engine = _engine(database)
    try:
        with engine.connect() as connection:
            return connection.execute(text(statement)).scalar_one()
    finally:
        engine.dispose()


def _rows(database: _Database, statement: str) -> list[tuple[object, ...]]:
    engine = _engine(database)
    try:
        with engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(statement)).all()]
    finally:
        engine.dispose()


def _relation(database: _Database, name: str) -> str | None:
    engine = _engine(database)
    try:
        with engine.connect() as connection:
            value = connection.execute(
                text("SELECT to_regclass(:name)"),
                {"name": f"public.{name}"},
            ).scalar_one()
    finally:
        engine.dispose()
    if value is None:
        return None
    return str(value)


def _expect_rejected(database: _Database, statement: str) -> None:
    engine = _engine(database)
    try:
        with engine.begin() as connection:
            connection.execute(text(statement))
    except IntegrityError:
        return
    except Exception as exc:
        raise AssertionError(f"Expected a constraint failure, got {type(exc).__name__}.") from None
    else:
        raise AssertionError("PostgreSQL accepted a row the migration should reject.")
    finally:
        engine.dispose()


def _clear_book(database: _Database) -> None:
    statement = "TRUNCATE TABLE " + ", ".join(_BOOK_TABLES) + " RESTART IDENTITY CASCADE"
    engine = _engine(database)
    try:
        with engine.begin() as connection:
            connection.execute(text(statement))
    finally:
        engine.dispose()


def _paper_settings(database: _Database) -> Settings:
    return Settings(execution_mode=ExecutionMode.PAPER, database_url=database.url)


def _request(
    key: str = "ci-paper-order-1",
    *,
    quantity: str = "4",
    price: str = "2",
    fee: str = "1",
) -> PaperOrderRequest:
    return PaperOrderRequest(
        strategy_id="core-slot",
        instrument=SolanaInstrument(USDC, "USDC", 6, 6, "SOL", 9),
        side=OrderSide.BUY,
        quantity=Decimal(quantity),
        reference_price=Decimal(price),
        outcome=SimulationOutcome.FILL,
        idempotency_key=key,
        fee_quote=Decimal(fee),
        slippage_quote=Decimal(0),
        shield_approved=False,
        risk=RiskIntent(
            mint=USDC,
            side=OrderSide.BUY.value,
            quantity=Decimal(quantity),
            reference_price=Decimal(price),
            fee_quote=Decimal(fee),
            slippage_quote=Decimal(0),
            size_decimals=6,
            price_decimals=6,
            quote_decimals=9,
            quote_symbol="SOL",
            stop_price=Decimal(price) / Decimal(2),
            equity_quote=Decimal(10000),
            sol_balance=Decimal(10000),
            valued_at=NOW,
            marks=(),
            liquidity_quote=Decimal(100000),
            volatility=None,
            confidence=None,
            token_age_seconds=None,
            market_condition=None,
            security="clear",
            creator="DeskWallet",
            narrative="momentum",
            liquidity_provider=None,
            driver=None,
            estimated_impact=None,
            exit_kind=ExitKind.ENTRY.value,
            signal_ref=None,
            emergency=None,
        ),
    )


@pytest.fixture(scope="module")
def migrated_postgres() -> _Database:
    url = _test_database_url()
    if url is None:
        pytest.skip("CYVORA_TEST_DATABASE_URL is not set, so PostgreSQL was not contacted.")
    database = _Database(url)
    major = int(str(_scalar(database, "SHOW server_version_num"))) // 10000
    if major != 17:
        raise AssertionError(f"PostgreSQL 17 is required. The server reported major {major}.")
    _reset_public(database)
    _run_alembic(database, "upgrade", "head")
    return database


def test_alembic_upgrade_downgrade_round_trip(migrated_postgres: _Database) -> None:
    url = migrated_postgres
    assert _scalar(url, "SELECT version_num FROM alembic_version") == "0008_readiness"
    assert _rows(
        url,
        "SELECT live_trading_enabled, authorization_state FROM readiness_controls WHERE id = 1",
    ) == [(False, "not_authorized")]
    _expect_rejected(
        url,
        "UPDATE readiness_controls SET live_trading_enabled = true WHERE id = 1",
    )
    _expect_rejected(
        url,
        "UPDATE readiness_controls SET authorization_state = 'live_authorized' WHERE id = 1",
    )
    _expect_rejected(
        url,
        "INSERT INTO shield_controls "
        "(id, consecutive_losses, breach_latched, breach_reasons, halt_entries, "
        "live_trading_enabled, limits_json, updated_at) "
        "VALUES (1, 0, false, '', false, true, '{}'::jsonb, CURRENT_TIMESTAMP)",
    )
    _expect_rejected(
        url,
        "INSERT INTO trading_orders "
        "(client_order_id, idempotency_key, strategy_id, mint, symbol, side, state, "
        "quantity, filled_quantity, reference_price, fee_quote, slippage_quote, "
        "quote_symbol, size_decimals, price_decimals, quote_decimals, outcome, "
        "shield_decision, simulated, execution_mode, created_at, updated_at) "
        "VALUES ('paper-live-state', 'live-state', 'core-slot', 'mint', 'USDC', 'BUY', "
        "'SUBMITTED', 1, 0, 1, 0, 0, 'SOL', 6, 6, 9, 'FILL', 'paper_approved', true, "
        "'PAPER', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
    )
    _expect_rejected(
        url,
        "INSERT INTO operation_recoveries "
        "(result, database_state, risk_state, position_status, entries_blocked, "
        "wallet_reconciliation, wallet_assumed_flat, live_trading_enabled, detail, "
        "started_at, finished_at) "
        "VALUES ('complete', 'reachable', 'loaded', 'matched', false, 'not_authorized', "
        "true, false, 'flat wallet refused', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
    )

    _run_alembic(url, "downgrade", "base")
    try:
        assert _relation(url, "trading_orders") is None
        assert _relation(url, "readiness_controls") is None
        assert _relation(url, "application_metadata") is None
        assert _rows(url, "SELECT version_num FROM alembic_version") == []
    finally:
        _run_alembic(url, "upgrade", "head")
    assert _scalar(url, "SELECT version_num FROM alembic_version") == "0008_readiness"
    assert _rows(
        url,
        "SELECT live_trading_enabled, authorization_state, kill_switch_engaged "
        "FROM readiness_controls WHERE id = 1",
    ) == [(False, "not_authorized", False)]


def test_paper_order_idempotency_keeps_one_fill(migrated_postgres: _Database) -> None:
    url = migrated_postgres
    _clear_book(url)
    latch = {"blocked": False}
    settings = _paper_settings(url)
    gateway = PaperExecutionGateway(
        ExecutionMode.PAPER,
        PostgresTradingRepository(settings),
        lambda: NOW,
        entries_blocked=lambda: latch["blocked"],
    )
    first = gateway.submit(_request())
    assert first.state is OrderState.CONFIRMED
    assert first.shield_decision == PAPER_APPROVED
    assert first.simulated is True
    assert first.filled_quantity == Decimal(4)
    second = gateway.submit(_request(quantity="99", fee="5"))
    assert second.client_order_id == first.client_order_id
    assert second.filled_quantity == Decimal(4)
    latch["blocked"] = True
    repeated = gateway.submit(_request(quantity="3", fee="0"))
    assert repeated.client_order_id == first.client_order_id
    with pytest.raises(TradingDisabled):
        gateway.submit(_request("ci-paper-order-2"))
    assert _scalar(url, "SELECT count(*) FROM trading_orders") == 1
    assert _rows(
        url,
        "SELECT state, simulated, execution_mode, shield_decision FROM trading_orders",
    ) == [("CONFIRMED", True, "PAPER", "paper_approved")]
    assert _scalar(url, "SELECT quantity FROM trading_positions") == Decimal(4)


def test_recovery_blocks_a_conflicting_book(migrated_postgres: _Database) -> None:
    url = migrated_postgres
    _clear_book(url)
    settings = _paper_settings(url)
    gateway = PaperExecutionGateway(
        ExecutionMode.PAPER,
        PostgresTradingRepository(settings),
        lambda: NOW,
    )
    order = gateway.submit(_request())
    assert order.state is OrderState.CONFIRMED
    matched = startup_recovery(settings, now=NOW)
    assert matched.result == "complete"
    assert matched.entries_blocked is False
    assert matched.position_status == "matched"
    assert matched.wallet_assumed_flat is False
    assert matched.live_trading_enabled is False
    assert matched.wallet_reconciliation == WALLET_NOT_AUTHORIZED

    engine = _engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("UPDATE trading_positions SET quantity = quantity + 1"))
    finally:
        engine.dispose()

    blocked = startup_recovery(settings, now=NOW)
    assert blocked.result == "blocked"
    assert blocked.entries_blocked is True
    assert blocked.position_status == "conflict"
    assert blocked.wallet_assumed_flat is False
    assert blocked.live_trading_enabled is False
    assert blocked.wallet_reconciliation == WALLET_NOT_AUTHORIZED
    assert _rows(
        url,
        "SELECT result, entries_blocked, wallet_assumed_flat, live_trading_enabled, "
        "wallet_reconciliation FROM operation_recoveries ORDER BY id",
    ) == [
        ("complete", False, False, False, WALLET_NOT_AUTHORIZED),
        ("blocked", True, False, False, WALLET_NOT_AUTHORIZED),
    ]
