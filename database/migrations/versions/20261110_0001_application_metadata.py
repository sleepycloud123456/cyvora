"""Create the application metadata table.

Revision ID: 0001_application_metadata
Revises:
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_application_metadata"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_metadata",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_name", sa.String(length=64), nullable=False),
        sa.Column("schema_revision", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("application_metadata")
