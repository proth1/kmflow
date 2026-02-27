"""ConflictObject model for cross-source inconsistency tracking and resolution.

Implements PRD v2.1 Section 6.10.5 (Cross-Source Consistency Checks) and
Section 6.3 Step 4/8 (Contradiction Resolution).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class MismatchType(enum.StrEnum):
    """Six mismatch types from the cross-source consistency checks."""

    SEQUENCE_MISMATCH = "sequence_mismatch"
    ROLE_MISMATCH = "role_mismatch"
    RULE_MISMATCH = "rule_mismatch"
    EXISTENCE_MISMATCH = "existence_mismatch"
    IO_MISMATCH = "io_mismatch"
    CONTROL_GAP = "control_gap"


class ResolutionType(enum.StrEnum):
    """Three-way resolution distinction for conflict objects."""

    GENUINE_DISAGREEMENT = "genuine_disagreement"
    NAMING_VARIANT = "naming_variant"
    TEMPORAL_SHIFT = "temporal_shift"


class ResolutionStatus(enum.StrEnum):
    """Resolution lifecycle states."""

    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class ConflictObject(Base):
    """A cross-source inconsistency detected during consistency checks.

    ConflictObjects are the primary output of Step 4 (Cross-Source Consistency
    Checks) and are resolved in Step 8 (Contradiction Resolution) of the
    Process POV Generator pipeline.
    """

    __tablename__ = "conflict_objects"
    __table_args__ = (
        Index("ix_conflict_objects_engagement_status", "engagement_id", "resolution_status"),
        Index("ix_conflict_objects_engagement_id", "engagement_id"),
        Index("ix_conflict_objects_source_a_id", "source_a_id"),
        Index("ix_conflict_objects_source_b_id", "source_b_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    mismatch_type: Mapped[MismatchType] = mapped_column(
        Enum(MismatchType, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    resolution_type: Mapped[ResolutionType | None] = mapped_column(
        Enum(ResolutionType, values_callable=lambda e: [x.value for x in e]), nullable=True
    )
    resolution_status: Mapped[ResolutionStatus] = mapped_column(
        Enum(ResolutionStatus, values_callable=lambda e: [x.value for x in e]),
        default=ResolutionStatus.UNRESOLVED,
        nullable=False,
    )
    source_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
    )
    source_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
    )
    severity: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    escalation_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ConflictObject(id={self.id}, type={self.mismatch_type}, "
            f"status={self.resolution_status})>"
        )
