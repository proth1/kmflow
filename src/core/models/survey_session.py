"""Survey session model for structured knowledge elicitation (Story #319)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class SurveySessionStatus(enum.StrEnum):
    """Survey session lifecycle states."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class SurveySession(Base):
    """A structured survey session for process knowledge elicitation."""

    __tablename__ = "survey_sessions"
    __table_args__ = (Index("ix_survey_sessions_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    respondent_role: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[SurveySessionStatus] = mapped_column(
        Enum(SurveySessionStatus, values_callable=lambda e: [x.value for x in e]),
        default=SurveySessionStatus.ACTIVE,
        nullable=False,
        server_default="active",
    )
    claims_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    claims: Mapped[list] = relationship(
        "SurveyClaim",
        primaryjoin="SurveySession.id == foreign(SurveyClaim.session_id)",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<SurveySession(id={self.id}, status={self.status}, claims={self.claims_count})>"
