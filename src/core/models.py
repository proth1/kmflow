"""SQLAlchemy ORM models for the KMFlow platform.

Core tables: engagements, evidence_items, evidence_fragments, audit_logs.
These match the data model from PRD Section 7.1.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class EngagementStatus(enum.StrEnum):
    """Status values for an engagement."""

    DRAFT = "draft"
    ACTIVE = "active"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class EvidenceCategory(enum.StrEnum):
    """The 12 evidence taxonomy categories from PRD Section 5."""

    DOCUMENTS = "documents"
    IMAGES = "images"
    AUDIO = "audio"
    VIDEO = "video"
    STRUCTURED_DATA = "structured_data"
    SAAS_EXPORTS = "saas_exports"
    KM4WORK = "km4work"
    BPM_PROCESS_MODELS = "bpm_process_models"
    REGULATORY_POLICY = "regulatory_policy"
    CONTROLS_EVIDENCE = "controls_evidence"
    DOMAIN_COMMUNICATIONS = "domain_communications"
    JOB_AIDS_EDGE_CASES = "job_aids_edge_cases"


class ValidationStatus(enum.StrEnum):
    """Evidence validation lifecycle states."""

    PENDING = "pending"
    VALIDATED = "validated"
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class FragmentType(enum.StrEnum):
    """Types of extracted evidence fragments."""

    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    ENTITY = "entity"
    RELATIONSHIP = "relationship"
    PROCESS_ELEMENT = "process_element"


class AuditAction(enum.StrEnum):
    """Audit log action types for engagement mutations."""

    ENGAGEMENT_CREATED = "engagement_created"
    ENGAGEMENT_UPDATED = "engagement_updated"
    ENGAGEMENT_ARCHIVED = "engagement_archived"


class Engagement(Base):
    """A consulting engagement scope."""

    __tablename__ = "engagements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client: Mapped[str] = mapped_column(String(255), nullable=False)
    business_area: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EngagementStatus] = mapped_column(
        Enum(EngagementStatus), default=EngagementStatus.DRAFT, nullable=False
    )
    team: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    evidence_items: Mapped[list[EvidenceItem]] = relationship(
        "EvidenceItem", back_populates="engagement", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog", back_populates="engagement", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Engagement(id={self.id}, name='{self.name}', client='{self.client}')>"


class EvidenceItem(Base):
    """An individual piece of evidence collected during an engagement."""

    __tablename__ = "evidence_items"
    __table_args__ = (Index("ix_evidence_engagement_category", "engagement_id", "category"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[EvidenceCategory] = mapped_column(Enum(EvidenceCategory), nullable=False)
    format: Mapped[str] = mapped_column(String(50), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Quality scores (0.0 - 1.0)
    completeness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reliability_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    consistency_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    validation_status: Mapped[ValidationStatus] = mapped_column(
        Enum(ValidationStatus), default=ValidationStatus.PENDING, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement", back_populates="evidence_items")
    fragments: Mapped[list[EvidenceFragment]] = relationship(
        "EvidenceFragment", back_populates="evidence_item", cascade="all, delete-orphan"
    )

    @property
    def quality_score(self) -> float:
        """Composite quality score (average of 4 dimensions)."""
        return (self.completeness_score + self.reliability_score + self.freshness_score + self.consistency_score) / 4.0

    def __repr__(self) -> str:
        return f"<EvidenceItem(id={self.id}, name='{self.name}', category={self.category})>"


class EvidenceFragment(Base):
    """An extracted component from an evidence item.

    Includes a vector embedding for semantic search via pgvector.
    """

    __tablename__ = "evidence_fragments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    fragment_type: Mapped[FragmentType] = mapped_column(Enum(FragmentType), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    evidence_item: Mapped[EvidenceItem] = relationship("EvidenceItem", back_populates="fragments")

    def __repr__(self) -> str:
        return f"<EvidenceFragment(id={self.id}, type={self.fragment_type})>"


class AuditLog(Base):
    """Audit log for tracking engagement mutation operations."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement", back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action}, engagement_id={self.engagement_id})>"
