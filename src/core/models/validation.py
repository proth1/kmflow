"""Validation models: ReviewPack and ReviewPackStatus (Story #349).

A ReviewPack represents a segment of a POV's activities bundled for SME
review. Each pack contains 3-8 activities, their evidence, confidence
scores, and conflict flags.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.core.models.engagement import Engagement


class ReviewPackStatus(enum.StrEnum):
    """Lifecycle status of a review pack."""

    PENDING = "pending"
    SENT = "sent"
    IN_REVIEW = "in_review"
    COMPLETE = "complete"


class ReviewPack(Base):
    """A segment-level review pack for SME validation.

    Groups 3-8 activities from a POV into a reviewable unit with
    supporting evidence, confidence scores, and conflict flags.
    """

    __tablename__ = "review_packs"
    __table_args__ = (
        Index("ix_review_packs_engagement_id", "engagement_id"),
        Index("ix_review_packs_pov_version_id", "pov_version_id"),
        Index("ix_review_packs_assigned_sme_id", "assigned_sme_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    pov_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_models.id", ondelete="CASCADE"), nullable=False
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    segment_activities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    activity_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    evidence_list: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    confidence_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    conflict_flags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    seed_terms: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    process_fragment_bpmn: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_sme_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), server_default="pending", nullable=False)
    avg_confidence: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engagement: Mapped["Engagement"] = relationship("Engagement")  # noqa: F821, UP037

    def __repr__(self) -> str:
        return f"<ReviewPack(id={self.id}, segment={self.segment_index}, activities={self.activity_count})>"
