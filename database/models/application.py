"""Schema identity stored in PostgreSQL."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class ApplicationMetadata(Base):
    """One row per applied foundation revision.

    Phase 1 creates the table and does not seed it until a local database
    exists and ``alembic upgrade head`` has been run by the operator.
    """

    __tablename__ = "application_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_name: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
