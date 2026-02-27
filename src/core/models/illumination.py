"""IlluminationAction model for targeted evidence acquisition planning."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class IlluminationActionType(enum.StrEnum):
    """Type of acquisition action for illuminating Dark segments."""

    SHELF_REQUEST = "shelf_request"
    PERSONA_PROBE = "persona_probe"
    SYSTEM_EXTRACT = "system_extract"


class IlluminationActionStatus(enum.StrEnum):
    """Status of an illumination action."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


class IlluminationAction(Base):
    """Tracks individual evidence acquisition actions for Dark segments.

    Each action targets a specific missing knowledge form and has a type
    (shelf request, persona probe, or system extraction). When all actions
    for a segment complete, confidence is recalculated.
    """

    __tablename__ = "illumination_actions"
    __table_args__ = (
        Index("ix_illumination_actions_engagement_id", "engagement_id"),
        Index("ix_illumination_actions_element_id", "element_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    element_id: Mapped[str] = mapped_column(String(512), nullable=False)
    element_name: Mapped[str] = mapped_column(String(512), nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_knowledge_form: Mapped[int] = mapped_column(nullable=False)
    target_form_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default=IlluminationActionStatus.PENDING, nullable=False
    )
    linked_item_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<IlluminationAction(id={self.id}, element='{self.element_name}', "
            f"type={self.action_type}, form={self.target_knowledge_form}, "
            f"status={self.status})>"
        )
