"""Grading snapshot model for tracking evidence grade distribution (Story #357).

Captures per-version grade distribution (U/D/C/B/A counts) and improvement
metrics for the Evidence Grading Progression KPI.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class GradingSnapshot(Base):
    """Snapshot of evidence grade distribution for a POV version.

    Tracks counts per grade (U/D/C/B/A) and the improvement percentage
    relative to the prior version.
    """

    __tablename__ = "grading_snapshots"
    __table_args__ = (
        Index("ix_grading_snapshots_engagement_id", "engagement_id"),
        Index("ix_grading_snapshots_pov_version_id", "pov_version_id"),
        UniqueConstraint(
            "engagement_id", "version_number",
            name="uq_grading_snapshots_engagement_version",
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
    grade_u: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    grade_d: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    grade_c: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    grade_b: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    grade_a: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    total_elements: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    improvement_pct: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    pov_version = relationship("ProcessModel")

    def __repr__(self) -> str:
        return (
            f"<GradingSnapshot(v{self.version_number}, "
            f"U={self.grade_u} D={self.grade_d} C={self.grade_c} "
            f"B={self.grade_b} A={self.grade_a})>"
        )
