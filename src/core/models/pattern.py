"""Pattern models: PatternCategory enum, PatternLibraryEntry, PatternAccessRule."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class PatternCategory(enum.StrEnum):
    """Categories for cross-engagement patterns."""

    PROCESS_OPTIMIZATION = "process_optimization"
    CONTROL_IMPROVEMENT = "control_improvement"
    TECHNOLOGY_ENABLEMENT = "technology_enablement"
    ORGANIZATIONAL_CHANGE = "organizational_change"
    RISK_MITIGATION = "risk_mitigation"


class PatternLibraryEntry(Base):
    """An anonymized cross-engagement reusable pattern."""

    __tablename__ = "pattern_library_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[PatternCategory] = mapped_column(
        Enum(PatternCategory, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    anonymized_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    usage_count: Mapped[int] = mapped_column(default=0, nullable=False)
    effectiveness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<PatternLibraryEntry(id={self.id}, title='{self.title}', category={self.category})>"


class PatternAccessRule(Base):
    """Controls which engagements can consume patterns."""

    __tablename__ = "pattern_access_rules"
    __table_args__ = (
        UniqueConstraint("pattern_id", "engagement_id", name="uq_pattern_engagement"),
        Index("ix_pattern_access_rules_pattern_id", "pattern_id"),
        Index("ix_pattern_access_rules_engagement_id", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pattern_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pattern_library_entries.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    granted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<PatternAccessRule(pattern_id={self.pattern_id}, engagement_id={self.engagement_id})>"
