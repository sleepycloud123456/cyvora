"""Allow the paper strategy and paper trader worker rows.

Revision ID: 0011_worker_kinds
Revises: 0010_paper_trader
Create Date: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_worker_kinds"
down_revision: str | None = "0010_paper_trader"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS = (
    "kind IN ('radar', 'portfolio', 'freshness', 'notifications', 'paper_strategy', 'paper_trader')"
)
_PREVIOUS = "kind IN ('radar', 'portfolio', 'freshness', 'notifications')"


def upgrade() -> None:
    op.drop_constraint("ck_operation_workers_kind", "operation_workers", type_="check")
    op.create_check_constraint("ck_operation_workers_kind", "operation_workers", _KINDS)


def downgrade() -> None:
    op.execute("DELETE FROM operation_heartbeats WHERE kind IN ('paper_strategy', 'paper_trader')")
    op.execute("DELETE FROM operation_workers WHERE kind IN ('paper_strategy', 'paper_trader')")
    op.drop_constraint("ck_operation_workers_kind", "operation_workers", type_="check")
    op.create_check_constraint("ck_operation_workers_kind", "operation_workers", _PREVIOUS)
