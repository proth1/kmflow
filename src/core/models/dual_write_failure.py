"""DualWriteFailure model for tracking failed cross-store writes.

When a write to Neo4j (or any secondary store) fails after the primary
PostgreSQL write has already committed, the failure is recorded here so
that a compensation job can retry the secondary write.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class DualWriteFailure(Base):
    """Track failed dual-writes for compensation retry."""

    __tablename__ = "dual_write_failures"
    __table_args__ = (
        Index("ix_dual_write_failures_source_table_id", "source_table", "source_id"),
        Index("ix_dual_write_failures_retried_created", "retried", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_table: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    target: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retried: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
