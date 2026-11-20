"""Allow paper-trader decisions to record an unpriced write-off exit.

Revision ID: 0012_paper_trader_exited
Revises: 0011_worker_kinds
Create Date: 2026-11-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_paper_trader_exited"
down_revision: str | None = "0011_worker_kinds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIONS = "action IN ('submitted', 'refused', 'blocked', 'held', 'duplicate', 'skipped', 'exited')"
_PREVIOUS = "action IN ('submitted', 'refused', 'blocked', 'held', 'duplicate', 'skipped')"


def upgrade() -> None:
    op.drop_constraint("ck_paper_trader_decisions_action", "paper_trader_decisions", type_="check")
    op.create_check_constraint(
        "ck_paper_trader_decisions_action", "paper_trader_decisions", _ACTIONS
    )


def downgrade() -> None:
    op.execute("DELETE FROM paper_trader_decisions WHERE action = 'exited'")
    op.drop_constraint("ck_paper_trader_decisions_action", "paper_trader_decisions", type_="check")
    op.create_check_constraint(
        "ck_paper_trader_decisions_action", "paper_trader_decisions", _PREVIOUS
    )
