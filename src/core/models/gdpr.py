"""GDPR compliance models (Story #317).

Data classification access control, lawful basis tracking for processing
activities, and per-engagement retention policies. Supports GDPR Articles
6, 15, 17, 20 and Article 30 Records of Processing Activities (ROPA).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class LawfulBasis(enum.StrEnum):
    """GDPR Article 6(1) lawful bases for data processing."""

    CONSENT = "consent"
    CONTRACT = "contract"
    LEGAL_OBLIGATION = "legal_obligation"
    VITAL_INTERESTS = "vital_interests"
    PUBLIC_TASK = "public_task"
    LEGITIMATE_INTERESTS = "legitimate_interests"


class RetentionAction(enum.StrEnum):
    """What happens when retention period expires."""

    ARCHIVE = "archive"
    DELETE = "delete"


class DataProcessingActivity(Base):
    """GDPR Article 30 Record of Processing Activity (ROPA).

    Documents each data processing activity, its lawful basis under
    Article 6, and links it to a specific engagement.
    """

    __tablename__ = "data_processing_activities"
    __table_args__ = (Index("ix_data_processing_activities_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    lawful_basis: Mapped[LawfulBasis] = mapped_column(Enum(LawfulBasis), nullable=False)
    article_6_basis: Mapped[str] = mapped_column(String(50), nullable=False, default="Art. 6(1)(f)")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<DataProcessingActivity(id={self.id}, name={self.name}, basis={self.lawful_basis})>"


class RetentionPolicy(Base):
    """Per-engagement data retention policy.

    Configures how long evidence is retained before archival or deletion.
    When the retention cleanup job runs, evidence items older than
    retention_days for the engagement are processed per the action.
    """

    __tablename__ = "retention_policies"
    __table_args__ = (Index("ix_retention_policies_engagement_id", "engagement_id", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    action: Mapped[RetentionAction] = mapped_column(
        Enum(RetentionAction), nullable=False, default=RetentionAction.ARCHIVE
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<RetentionPolicy(engagement={self.engagement_id}, days={self.retention_days}, action={self.action})>"
