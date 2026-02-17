"""SQLAlchemy ORM models for the KMFlow platform.

Core tables: engagements, evidence_items, evidence_fragments, audit_logs,
shelf_data_requests, shelf_data_request_items.
These match the data model from PRD Section 7.1.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Date,
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
    EVIDENCE_UPLOADED = "evidence_uploaded"
    EVIDENCE_VALIDATED = "evidence_validated"
    SHELF_REQUEST_CREATED = "shelf_request_created"
    SHELF_REQUEST_UPDATED = "shelf_request_updated"


class ShelfRequestStatus(enum.StrEnum):
    """Status values for a shelf data request."""

    DRAFT = "draft"
    SENT = "sent"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"


class ShelfRequestItemStatus(enum.StrEnum):
    """Status values for a shelf data request item."""

    PENDING = "pending"
    RECEIVED = "received"
    OVERDUE = "overdue"


class ShelfRequestItemPriority(enum.StrEnum):
    """Priority values for a shelf data request item."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


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
    shelf_data_requests: Mapped[list[ShelfDataRequest]] = relationship(
        "ShelfDataRequest", back_populates="engagement", cascade="all, delete-orphan"
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

    # File storage fields
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Metadata
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    # Quality scores (0.0 - 1.0)
    completeness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reliability_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    freshness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    consistency_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Duplicate detection
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
    )

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


class ShelfDataRequest(Base):
    """A shelf data request sent to a client to gather evidence."""

    __tablename__ = "shelf_data_requests"
    __table_args__ = (Index("ix_shelf_requests_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ShelfRequestStatus] = mapped_column(
        Enum(ShelfRequestStatus), default=ShelfRequestStatus.DRAFT, nullable=False
    )
    due_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement", back_populates="shelf_data_requests")
    items: Mapped[list[ShelfDataRequestItem]] = relationship(
        "ShelfDataRequestItem", back_populates="request", cascade="all, delete-orphan"
    )

    @property
    def fulfillment_percentage(self) -> float:
        """Calculate the percentage of items that have been received."""
        if not self.items:
            return 0.0
        received = sum(1 for item in self.items if item.status == ShelfRequestItemStatus.RECEIVED)
        return round(received / len(self.items) * 100.0, 2)

    def __repr__(self) -> str:
        return f"<ShelfDataRequest(id={self.id}, title='{self.title}', status={self.status})>"


class ProcessModelStatus(enum.StrEnum):
    """Status values for a process model."""

    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessElementType(enum.StrEnum):
    """Types of process elements in a POV model."""

    ACTIVITY = "activity"
    GATEWAY = "gateway"
    EVENT = "event"
    ROLE = "role"
    SYSTEM = "system"
    DOCUMENT = "document"


class CorroborationLevel(enum.StrEnum):
    """Corroboration levels for process elements."""

    STRONGLY = "strongly"
    MODERATELY = "moderately"
    WEAKLY = "weakly"


class GapType(enum.StrEnum):
    """Types of evidence gaps."""

    MISSING_DATA = "missing_data"
    WEAK_EVIDENCE = "weak_evidence"
    SINGLE_SOURCE = "single_source"


class GapSeverity(enum.StrEnum):
    """Severity levels for evidence gaps."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProcessModel(Base):
    """A generated Process Point of View model from the LCD algorithm."""

    __tablename__ = "process_models"
    __table_args__ = (Index("ix_process_models_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    scope: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[ProcessModelStatus] = mapped_column(
        Enum(ProcessModelStatus), default=ProcessModelStatus.GENERATING, nullable=False
    )
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    bpmn_xml: Mapped[str | None] = mapped_column(Text, nullable=True)
    element_count: Mapped[int] = mapped_column(default=0, nullable=False)
    evidence_count: Mapped[int] = mapped_column(default=0, nullable=False)
    contradiction_count: Mapped[int] = mapped_column(default=0, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_by: Mapped[str] = mapped_column(String(255), default="lcd_algorithm", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement")
    elements: Mapped[list[ProcessElement]] = relationship(
        "ProcessElement", back_populates="process_model", cascade="all, delete-orphan"
    )
    contradictions: Mapped[list[Contradiction]] = relationship(
        "Contradiction", back_populates="process_model", cascade="all, delete-orphan"
    )
    evidence_gaps: Mapped[list[EvidenceGap]] = relationship(
        "EvidenceGap", back_populates="process_model", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ProcessModel(id={self.id}, scope='{self.scope}', status={self.status})>"


class ProcessElement(Base):
    """An element within a generated process model."""

    __tablename__ = "process_elements"
    __table_args__ = (Index("ix_process_elements_model_id", "model_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_models.id", ondelete="CASCADE"), nullable=False
    )
    element_type: Mapped[ProcessElementType] = mapped_column(Enum(ProcessElementType), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    triangulation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    corroboration_level: Mapped[CorroborationLevel] = mapped_column(
        Enum(CorroborationLevel), default=CorroborationLevel.WEAKLY, nullable=False
    )
    evidence_count: Mapped[int] = mapped_column(default=0, nullable=False)
    evidence_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    process_model: Mapped[ProcessModel] = relationship("ProcessModel", back_populates="elements")

    def __repr__(self) -> str:
        return f"<ProcessElement(id={self.id}, name='{self.name}', type={self.element_type})>"


class Contradiction(Base):
    """A detected contradiction between evidence sources."""

    __tablename__ = "contradictions"
    __table_args__ = (Index("ix_contradictions_model_id", "model_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_models.id", ondelete="CASCADE"), nullable=False
    )
    element_name: Mapped[str] = mapped_column(String(512), nullable=False)
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    values: Mapped[list | None] = mapped_column(JSON, nullable=True)
    resolution_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    process_model: Mapped[ProcessModel] = relationship("ProcessModel", back_populates="contradictions")

    def __repr__(self) -> str:
        return f"<Contradiction(id={self.id}, element='{self.element_name}', field='{self.field_name}')>"


class EvidenceGap(Base):
    """An identified gap in evidence coverage."""

    __tablename__ = "evidence_gaps"
    __table_args__ = (Index("ix_evidence_gaps_model_id", "model_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_models.id", ondelete="CASCADE"), nullable=False
    )
    gap_type: Mapped[GapType] = mapped_column(Enum(GapType), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[GapSeverity] = mapped_column(Enum(GapSeverity), default=GapSeverity.MEDIUM, nullable=False)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_element_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_elements.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    process_model: Mapped[ProcessModel] = relationship("ProcessModel", back_populates="evidence_gaps")

    def __repr__(self) -> str:
        return f"<EvidenceGap(id={self.id}, type={self.gap_type}, severity={self.severity})>"


class ShelfDataRequestItem(Base):
    """An individual item requested within a shelf data request."""

    __tablename__ = "shelf_data_request_items"
    __table_args__ = (Index("ix_shelf_request_items_request_id", "request_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shelf_data_requests.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[EvidenceCategory] = mapped_column(Enum(EvidenceCategory), nullable=False)
    item_name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[ShelfRequestItemPriority] = mapped_column(
        Enum(ShelfRequestItemPriority), default=ShelfRequestItemPriority.MEDIUM, nullable=False
    )
    status: Mapped[ShelfRequestItemStatus] = mapped_column(
        Enum(ShelfRequestItemStatus), default=ShelfRequestItemStatus.PENDING, nullable=False
    )
    matched_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    request: Mapped[ShelfDataRequest] = relationship("ShelfDataRequest", back_populates="items")

    def __repr__(self) -> str:
        return f"<ShelfDataRequestItem(id={self.id}, name='{self.item_name}', status={self.status})>"
