"""Dark Room snapshot model for tracking brightness distribution across POV versions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class DarkRoomSnapshot(Base):
    """Snapshot of dark/dim/bright segment counts for a POV version.

    Used to track the Dark-Room Shrink Rate KPI across validation cycles.
    A new snapshot is created each time a POV version is generated or validated.
    """

    __tablename__ = "dark_room_snapshots"
    __table_args__ = (
        Index("ix_dark_room_snapshots_engagement_id", "engagement_id"),
        Index("ix_dark_room_snapshots_pov_version_id", "pov_version_id"),
        UniqueConstraint(
            "engagement_id", "version_number",
            name="uq_dark_room_snapshots_engagement_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    pov_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_models.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    dark_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    dim_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    bright_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    total_elements: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships (string-only for cross-module reference)
    pov_version = relationship("ProcessModel")

    def __repr__(self) -> str:
        return (
            f"<DarkRoomSnapshot(id={self.id}, v{self.version_number}, "
            f"dark={self.dark_count}, dim={self.dim_count}, bright={self.bright_count})>"
        )
