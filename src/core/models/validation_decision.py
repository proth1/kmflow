"""ValidationDecision model for structured reviewer actions (Story #353).

Captures SME decisions on review pack items: CONFIRM, CORRECT, REJECT, DEFER.
Each decision triggers a corresponding knowledge graph write-back action.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class ReviewerAction(enum.StrEnum):
    """Four structured reviewer actions."""

    CONFIRM = "confirm"
    CORRECT = "correct"
    REJECT = "reject"
    DEFER = "defer"


class ValidationDecision(Base):
    """A reviewer's decision on a review pack item.

    Records the action taken (CONFIRM/CORRECT/REJECT/DEFER),
    the reviewer, and the decision payload for graph write-back.
    """

    __tablename__ = "validation_decisions"
    __table_args__ = (
        Index("ix_validation_decisions_review_pack_id", "review_pack_id"),
        Index("ix_validation_decisions_engagement_id", "engagement_id"),
        Index("ix_validation_decisions_reviewer_id", "reviewer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    review_pack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review_packs.id", ondelete="CASCADE"),
        nullable=False,
    )
    element_id: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    action: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    payload: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )
    graph_write_back_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )
    reasoning: Mapped[str | None] = mapped_column(
        String(2000), nullable=True
    )
    evidence_refs: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )
    confidence_before: Mapped[float | None] = mapped_column(
        nullable=True
    )
    confidence_after: Mapped[float | None] = mapped_column(
        nullable=True
    )
    decision_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    review_pack: Mapped["ReviewPack"] = relationship("ReviewPack")  # noqa: F821, UP037

    def __repr__(self) -> str:
        return (
            f"<ValidationDecision(id={self.id}, action={self.action}, "
            f"element={self.element_id})>"
        )
