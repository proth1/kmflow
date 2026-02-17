"""SQLAlchemy ORM models for the KMFlow platform.

Core tables: engagements, evidence_items, evidence_fragments, audit_logs,
shelf_data_requests, shelf_data_request_items, policies, controls, regulations,
target_operating_models, gap_analysis_results, best_practices, benchmarks.
These match the data model from PRD Section 7.1 (Phase 1) and Section 7.2 (Phase 2).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
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


class UserRole(enum.StrEnum):
    """User role levels for RBAC."""

    PLATFORM_ADMIN = "platform_admin"
    ENGAGEMENT_LEAD = "engagement_lead"
    PROCESS_ANALYST = "process_analyst"
    EVIDENCE_REVIEWER = "evidence_reviewer"
    CLIENT_VIEWER = "client_viewer"


class AuditAction(enum.StrEnum):
    """Audit log action types for engagement mutations."""

    ENGAGEMENT_CREATED = "engagement_created"
    ENGAGEMENT_UPDATED = "engagement_updated"
    ENGAGEMENT_ARCHIVED = "engagement_archived"
    EVIDENCE_UPLOADED = "evidence_uploaded"
    EVIDENCE_VALIDATED = "evidence_validated"
    SHELF_REQUEST_CREATED = "shelf_request_created"
    SHELF_REQUEST_UPDATED = "shelf_request_updated"
    LOGIN = "login"
    LOGOUT = "logout"
    PERMISSION_DENIED = "permission_denied"
    DATA_ACCESS = "data_access"
    POV_GENERATED = "pov_generated"
    POLICY_CREATED = "policy_created"
    CONTROL_CREATED = "control_created"
    REGULATION_CREATED = "regulation_created"
    TOM_CREATED = "tom_created"
    GAP_ANALYSIS_RUN = "gap_analysis_run"
    REPORT_GENERATED = "report_generated"
    # -- Phase 3: Monitoring / Alerting / Patterns / Simulation -----------------
    INTEGRATION_CONNECTED = "integration_connected"
    INTEGRATION_SYNCED = "integration_synced"
    MONITORING_CONFIGURED = "monitoring_configured"
    MONITORING_ACTIVATED = "monitoring_activated"
    MONITORING_STOPPED = "monitoring_stopped"
    ALERT_GENERATED = "alert_generated"
    ALERT_ACKNOWLEDGED = "alert_acknowledged"
    ALERT_RESOLVED = "alert_resolved"
    AGENT_GAP_SCAN = "agent_gap_scan"
    PATTERN_CREATED = "pattern_created"
    PATTERN_APPLIED = "pattern_applied"
    SIMULATION_CREATED = "simulation_created"
    SIMULATION_EXECUTED = "simulation_executed"


# -- Phase 2: Regulatory / Policy / Control enums ----------------------------


class PolicyType(enum.StrEnum):
    """Types of policies that govern processes."""

    ORGANIZATIONAL = "organizational"
    REGULATORY = "regulatory"
    OPERATIONAL = "operational"
    SECURITY = "security"


class ControlEffectiveness(enum.StrEnum):
    """Effectiveness rating for controls."""

    HIGHLY_EFFECTIVE = "highly_effective"
    EFFECTIVE = "effective"
    MODERATELY_EFFECTIVE = "moderately_effective"
    INEFFECTIVE = "ineffective"


class ComplianceLevel(enum.StrEnum):
    """Compliance assessment levels."""

    FULLY_COMPLIANT = "fully_compliant"
    PARTIALLY_COMPLIANT = "partially_compliant"
    NON_COMPLIANT = "non_compliant"
    NOT_ASSESSED = "not_assessed"


# -- Phase 2: TOM enums -------------------------------------------------------


class TOMDimension(enum.StrEnum):
    """Target Operating Model dimensions."""

    PROCESS_ARCHITECTURE = "process_architecture"
    PEOPLE_AND_ORGANIZATION = "people_and_organization"
    TECHNOLOGY_AND_DATA = "technology_and_data"
    GOVERNANCE_STRUCTURES = "governance_structures"
    PERFORMANCE_MANAGEMENT = "performance_management"
    RISK_AND_COMPLIANCE = "risk_and_compliance"


class TOMGapType(enum.StrEnum):
    """Types of TOM gaps."""

    FULL_GAP = "full_gap"
    PARTIAL_GAP = "partial_gap"
    DEVIATION = "deviation"
    NO_GAP = "no_gap"


class ProcessMaturity(enum.StrEnum):
    """Process maturity levels (CMMI-inspired)."""

    INITIAL = "initial"
    MANAGED = "managed"
    DEFINED = "defined"
    QUANTITATIVELY_MANAGED = "quantitatively_managed"
    OPTIMIZING = "optimizing"


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


class User(Base):
    """A platform user with role-based access control."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.PROCESS_ANALYST, insert_default=UserRole.PROCESS_ANALYST, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, insert_default=True, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    engagement_memberships: Mapped[list[EngagementMember]] = relationship(
        "EngagementMember", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role={self.role})>"


class EngagementMember(Base):
    """Links users to engagements with a role-in-engagement override."""

    __tablename__ = "engagement_members"
    __table_args__ = (
        UniqueConstraint("engagement_id", "user_id", name="uq_engagement_user"),
        Index("ix_engagement_members_engagement_id", "engagement_id"),
        Index("ix_engagement_members_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_in_engagement: Mapped[str] = mapped_column(String(100), nullable=False, default="member")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement")
    user: Mapped[User] = relationship("User", back_populates="engagement_memberships")

    def __repr__(self) -> str:
        return f"<EngagementMember(engagement_id={self.engagement_id}, user_id={self.user_id})>"


# =============================================================================
# Phase 2: Regulatory / Policy / Control models
# =============================================================================


class Policy(Base):
    """A policy that governs processes within an engagement."""

    __tablename__ = "policies"
    __table_args__ = (Index("ix_policies_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    policy_type: Mapped[PolicyType] = mapped_column(Enum(PolicyType), nullable=False)
    source_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
    )
    clauses: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<Policy(id={self.id}, name='{self.name}', type={self.policy_type})>"


class Control(Base):
    """A control that enforces policies within an engagement."""

    __tablename__ = "controls"
    __table_args__ = (Index("ix_controls_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    effectiveness: Mapped[ControlEffectiveness] = mapped_column(
        Enum(ControlEffectiveness), default=ControlEffectiveness.EFFECTIVE, nullable=False
    )
    effectiveness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    linked_policy_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<Control(id={self.id}, name='{self.name}', effectiveness={self.effectiveness})>"


class Regulation(Base):
    """A regulation or compliance framework relevant to an engagement."""

    __tablename__ = "regulations"
    __table_args__ = (Index("ix_regulations_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    framework: Mapped[str | None] = mapped_column(String(255), nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(255), nullable=True)
    obligations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<Regulation(id={self.id}, name='{self.name}', framework='{self.framework}')>"


# =============================================================================
# Phase 2: TOM models
# =============================================================================


class TargetOperatingModel(Base):
    """A Target Operating Model definition for an engagement."""

    __tablename__ = "target_operating_models"
    __table_args__ = (Index("ix_tom_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    dimensions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    maturity_targets: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement")
    gap_results: Mapped[list[GapAnalysisResult]] = relationship(
        "GapAnalysisResult", back_populates="tom", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<TargetOperatingModel(id={self.id}, name='{self.name}')>"


class GapAnalysisResult(Base):
    """A gap identified between current state and TOM target."""

    __tablename__ = "gap_analysis_results"
    __table_args__ = (
        Index("ix_gap_results_engagement_id", "engagement_id"),
        Index("ix_gap_results_tom_id", "tom_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    tom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("target_operating_models.id", ondelete="CASCADE"), nullable=False
    )
    gap_type: Mapped[TOMGapType] = mapped_column(Enum(TOMGapType), nullable=False)
    dimension: Mapped[TOMDimension] = mapped_column(Enum(TOMDimension), nullable=False)
    severity: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement")
    tom: Mapped[TargetOperatingModel] = relationship("TargetOperatingModel", back_populates="gap_results")

    @property
    def priority_score(self) -> float:
        """Computed priority: severity * confidence."""
        return round(self.severity * self.confidence, 4)

    def __repr__(self) -> str:
        return f"<GapAnalysisResult(id={self.id}, gap_type={self.gap_type}, dimension={self.dimension})>"


class BestPractice(Base):
    """An industry best practice for TOM alignment benchmarking."""

    __tablename__ = "best_practices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tom_dimension: Mapped[TOMDimension] = mapped_column(Enum(TOMDimension), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<BestPractice(id={self.id}, domain='{self.domain}', industry='{self.industry}')>"


class Benchmark(Base):
    """An industry benchmark for process performance comparison."""

    __tablename__ = "benchmarks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str] = mapped_column(String(255), nullable=False)
    p25: Mapped[float] = mapped_column(Float, nullable=False)
    p50: Mapped[float] = mapped_column(Float, nullable=False)
    p75: Mapped[float] = mapped_column(Float, nullable=False)
    p90: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Benchmark(id={self.id}, metric='{self.metric_name}', industry='{self.industry}')>"


# =============================================================================
# Phase 3: Monitoring / Alerting / Patterns / Simulation enums
# =============================================================================


class MonitoringStatus(enum.StrEnum):
    """Status of a monitoring job."""

    CONFIGURING = "configuring"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


class AlertSeverity(enum.StrEnum):
    """Severity levels for monitoring alerts."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertStatus(enum.StrEnum):
    """Lifecycle status of a monitoring alert."""

    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class DeviationCategory(enum.StrEnum):
    """Categories of process deviations."""

    SEQUENCE_CHANGE = "sequence_change"
    MISSING_ACTIVITY = "missing_activity"
    NEW_ACTIVITY = "new_activity"
    ROLE_CHANGE = "role_change"
    TIMING_ANOMALY = "timing_anomaly"
    FREQUENCY_CHANGE = "frequency_change"
    CONTROL_BYPASS = "control_bypass"


class MonitoringSourceType(enum.StrEnum):
    """Types of monitoring data sources."""

    EVENT_LOG = "event_log"
    TASK_MINING = "task_mining"
    SYSTEM_API = "system_api"
    FILE_WATCH = "file_watch"


class SimulationStatus(enum.StrEnum):
    """Lifecycle status of a simulation run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SimulationType(enum.StrEnum):
    """Types of process simulation scenarios."""

    WHAT_IF = "what_if"
    CAPACITY = "capacity"
    PROCESS_CHANGE = "process_change"
    CONTROL_REMOVAL = "control_removal"


class PatternCategory(enum.StrEnum):
    """Categories for cross-engagement patterns."""

    PROCESS_OPTIMIZATION = "process_optimization"
    CONTROL_IMPROVEMENT = "control_improvement"
    TECHNOLOGY_ENABLEMENT = "technology_enablement"
    ORGANIZATIONAL_CHANGE = "organizational_change"
    RISK_MITIGATION = "risk_mitigation"


# =============================================================================
# Phase 3: Integration Persistence
# =============================================================================


class IntegrationConnection(Base):
    """Persisted integration connection configuration (replaces in-memory dict)."""

    __tablename__ = "integration_connections"
    __table_args__ = (Index("ix_integration_connections_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    connector_type: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="configured", nullable=False)
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    encrypted_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_mappings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_records: Mapped[int] = mapped_column(default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<IntegrationConnection(id={self.id}, type='{self.connector_type}', name='{self.name}')>"


# =============================================================================
# Phase 3: Monitoring models
# =============================================================================


class ProcessBaseline(Base):
    """Frozen snapshot of process model state for comparison."""

    __tablename__ = "process_baselines"
    __table_args__ = (Index("ix_process_baselines_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    process_model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_models.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    snapshot_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    element_count: Mapped[int] = mapped_column(default=0, nullable=False)
    process_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<ProcessBaseline(id={self.id}, name='{self.name}')>"


class MonitoringJob(Base):
    """Monitoring configuration per engagement+source."""

    __tablename__ = "monitoring_jobs"
    __table_args__ = (Index("ix_monitoring_jobs_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_connections.id", ondelete="SET NULL"), nullable=True
    )
    baseline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_baselines.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[MonitoringSourceType] = mapped_column(Enum(MonitoringSourceType), nullable=False)
    status: Mapped[MonitoringStatus] = mapped_column(
        Enum(MonitoringStatus), default=MonitoringStatus.CONFIGURING, nullable=False
    )
    schedule_cron: Mapped[str] = mapped_column(String(100), default="0 0 * * *", nullable=False)
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<MonitoringJob(id={self.id}, name='{self.name}', status={self.status})>"


# =============================================================================
# Phase 3: Deviation Detection
# =============================================================================


class ProcessDeviation(Base):
    """A detected deviation from baseline process model."""

    __tablename__ = "process_deviations"
    __table_args__ = (
        Index("ix_process_deviations_job_id", "monitoring_job_id"),
        Index("ix_process_deviations_engagement_id", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    monitoring_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitoring_jobs.id", ondelete="CASCADE"), nullable=False
    )
    baseline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_baselines.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[DeviationCategory] = mapped_column(Enum(DeviationCategory), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    affected_element: Mapped[str | None] = mapped_column(String(512), nullable=True)
    magnitude: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<ProcessDeviation(id={self.id}, category={self.category}, magnitude={self.magnitude})>"


# =============================================================================
# Phase 3: Alerting
# =============================================================================


class MonitoringAlert(Base):
    """An alert triggered by process deviations."""

    __tablename__ = "monitoring_alerts"
    __table_args__ = (
        Index("ix_monitoring_alerts_engagement_id", "engagement_id"),
        Index("ix_monitoring_alerts_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    monitoring_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitoring_jobs.id", ondelete="CASCADE"), nullable=False
    )
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity), nullable=False)
    status: Mapped[AlertStatus] = mapped_column(Enum(AlertStatus), default=AlertStatus.NEW, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    deviation_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    dedup_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<MonitoringAlert(id={self.id}, severity={self.severity}, status={self.status})>"


# =============================================================================
# Phase 3: Cross-Engagement Pattern Library
# =============================================================================


class PatternLibraryEntry(Base):
    """An anonymized cross-engagement reusable pattern."""

    __tablename__ = "pattern_library_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[PatternCategory] = mapped_column(Enum(PatternCategory), nullable=False)
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


# =============================================================================
# Phase 3: Process Simulation
# =============================================================================


class SimulationScenario(Base):
    """A what-if simulation scenario definition."""

    __tablename__ = "simulation_scenarios"
    __table_args__ = (Index("ix_simulation_scenarios_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    process_model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_models.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    simulation_type: Mapped[SimulationType] = mapped_column(Enum(SimulationType), nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<SimulationScenario(id={self.id}, name='{self.name}', type={self.simulation_type})>"


class SimulationResult(Base):
    """Output from a simulation run."""

    __tablename__ = "simulation_results"
    __table_args__ = (Index("ix_simulation_results_scenario_id", "scenario_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[SimulationStatus] = mapped_column(
        Enum(SimulationStatus), default=SimulationStatus.PENDING, nullable=False
    )
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    impact_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommendations: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    execution_time_ms: Mapped[int] = mapped_column(default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    scenario: Mapped[SimulationScenario] = relationship("SimulationScenario")

    def __repr__(self) -> str:
        return f"<SimulationResult(id={self.id}, status={self.status})>"


# =============================================================================
# Phase 4: MCP API Key Persistence
# =============================================================================


class MCPAPIKey(Base):
    """DB-persisted MCP API key for external tool access."""

    __tablename__ = "mcp_api_keys"
    __table_args__ = (
        UniqueConstraint("key_id", name="uq_mcp_api_keys_key_id"),
        Index("ix_mcp_api_keys_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship("User")

    def __repr__(self) -> str:
        return f"<MCPAPIKey(id={self.id}, key_id='{self.key_id}', client='{self.client_name}')>"


# =============================================================================
# Phase 4: Conformance Checking
# =============================================================================


class ReferenceProcessModel(Base):
    """BPMN reference model for conformance checking."""

    __tablename__ = "reference_process_models"
    __table_args__ = (Index("ix_reference_process_models_industry", "industry"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    industry: Mapped[str] = mapped_column(String(255), nullable=False)
    process_area: Mapped[str] = mapped_column(String(255), nullable=False)
    bpmn_xml: Mapped[str] = mapped_column(Text, nullable=False)
    graph_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<ReferenceProcessModel(id={self.id}, name='{self.name}')>"


class ConformanceResult(Base):
    """Output of a conformance check between observed and reference models."""

    __tablename__ = "conformance_results"
    __table_args__ = (
        Index("ix_conformance_results_engagement_id", "engagement_id"),
        Index("ix_conformance_results_reference_model_id", "reference_model_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    reference_model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reference_process_models.id", ondelete="CASCADE"), nullable=False
    )
    pov_model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_models.id", ondelete="SET NULL"), nullable=True
    )
    fitness_score: Mapped[float] = mapped_column(Float, nullable=False)
    precision_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    deviations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engagement: Mapped[Engagement] = relationship("Engagement")
    reference_model: Mapped[ReferenceProcessModel] = relationship("ReferenceProcessModel")

    def __repr__(self) -> str:
        return f"<ConformanceResult(id={self.id}, fitness={self.fitness_score})>"
