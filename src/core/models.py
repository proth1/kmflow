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
    SCENARIO_MODIFIED = "scenario_modified"
    SCENARIO_COMPARED = "scenario_compared"
    EPISTEMIC_PLAN_GENERATED = "epistemic_plan_generated"
    # -- Phase 4: Financial / Suggestions ----------------------------------------
    SUGGESTION_CREATED = "suggestion_created"
    SUGGESTION_ACCEPTED = "suggestion_accepted"
    SUGGESTION_REJECTED = "suggestion_rejected"
    FINANCIAL_ASSUMPTION_CREATED = "financial_assumption_created"
    # -- Cross-cutting audit actions ---------------------------------------------
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    MEMBER_ADDED = "member_added"
    MEMBER_REMOVED = "member_removed"
    ANNOTATION_CREATED = "annotation_created"
    ANNOTATION_UPDATED = "annotation_updated"
    ANNOTATION_DELETED = "annotation_deleted"
    CONFORMANCE_MODEL_CREATED = "conformance_model_created"
    CONFORMANCE_CHECK_RUN = "conformance_check_run"
    METRIC_DEFINED = "metric_defined"
    METRIC_READING_RECORDED = "metric_reading_recorded"
    METRICS_SEEDED = "metrics_seeded"
    PATTERN_UPDATED = "pattern_updated"
    PATTERN_DELETED = "pattern_deleted"
    PORTAL_UPLOAD = "portal_upload"
    BASELINE_CREATED = "baseline_created"


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
    retention_days: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=365)  # 365-day default satisfies data minimization; None = indefinite (not recommended)
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

    # Data lineage fields (Phase A: Data Layer Evolution)
    source_system: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delta_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    lineage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

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
    __table_args__ = (Index("ix_evidence_fragments_evidence_id", "evidence_id"),)

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

    # GDPR erasure fields (Issue #165)
    # Set when a user submits an erasure request; background job anonymizes
    # the account after erasure_scheduled_at passes the grace period.
    erasure_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    erasure_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)

    # Relationships
    engagement_memberships: Mapped[list[EngagementMember]] = relationship(
        "EngagementMember", back_populates="user", cascade="all, delete-orphan"
    )
    consents: Mapped[list[UserConsent]] = relationship(
        "UserConsent", back_populates="user", cascade="all, delete-orphan"
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
# GDPR: User consent tracking (Issue #165)
# =============================================================================


class UserConsent(Base):
    """Tracks a user's consent grant or revocation for a specific consent type.

    Each row represents one consent event. The current state is the most
    recent row for a given (user_id, consent_type) pair (highest granted_at).
    Consent changes are immutable records for audit purposes — never updated
    in place, only new rows inserted.
    """

    __tablename__ = "user_consents"
    __table_args__ = (Index("ix_user_consents_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # One of: "analytics", "data_processing", "marketing_communications"
    consent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    # IP address recorded for audit trail; nullable for cases where it is
    # not available (e.g. programmatic updates or legacy imports).
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True, default=None)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="consents")

    def __repr__(self) -> str:
        return f"<UserConsent(user_id={self.user_id}, type='{self.consent_type}', granted={self.granted})>"


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
    __table_args__ = (UniqueConstraint("domain", "industry", "tom_dimension", name="uq_best_practice_domain_industry_dimension"),)

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
    __table_args__ = (UniqueConstraint("metric_name", "industry", name="uq_benchmark_metric_industry"),)

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
# Phase 8: Success Metrics, Annotations
# =============================================================================


class MetricCategory(enum.StrEnum):
    """Categories for success metrics."""

    PROCESS_EFFICIENCY = "process_efficiency"
    QUALITY = "quality"
    COMPLIANCE = "compliance"
    CUSTOMER_SATISFACTION = "customer_satisfaction"
    COST = "cost"
    TIMELINESS = "timeliness"


class SuccessMetric(Base):
    """Definition of a success metric for engagement measurement."""

    __tablename__ = "success_metrics"
    __table_args__ = (UniqueConstraint("name", "category", name="uq_success_metric_name_category"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(100), nullable=False)
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[MetricCategory] = mapped_column(Enum(MetricCategory), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    readings: Mapped[list[MetricReading]] = relationship("MetricReading", back_populates="metric")

    def __repr__(self) -> str:
        return f"<SuccessMetric(id={self.id}, name='{self.name}', category='{self.category}')>"


class MetricReading(Base):
    """A recorded value for a success metric at a point in time."""

    __tablename__ = "metric_readings"
    __table_args__ = (
        Index("ix_metric_readings_metric_id", "metric_id"),
        Index("ix_metric_readings_engagement_id", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("success_metrics.id", ondelete="CASCADE"), nullable=False)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    metric: Mapped[SuccessMetric] = relationship("SuccessMetric", back_populates="readings")

    def __repr__(self) -> str:
        return f"<MetricReading(id={self.id}, metric_id={self.metric_id}, value={self.value})>"


class Annotation(Base):
    """SME annotation attached to engagement artifacts."""

    __tablename__ = "annotations"
    __table_args__ = (Index("ix_annotations_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    author_id: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Annotation(id={self.id}, target_type='{self.target_type}', target_id='{self.target_id}')>"


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


class ModificationType(enum.StrEnum):
    """Types of scenario modifications for the Scenario Comparison Workbench."""

    TASK_ADD = "task_add"
    TASK_REMOVE = "task_remove"
    TASK_MODIFY = "task_modify"
    ROLE_REASSIGN = "role_reassign"
    GATEWAY_RESTRUCTURE = "gateway_restructure"
    CONTROL_ADD = "control_add"
    CONTROL_REMOVE = "control_remove"


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
        Index("ix_monitoring_alerts_monitoring_job_id", "monitoring_job_id"),
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
    status: Mapped[str | None] = mapped_column(String(50), nullable=True, server_default="draft")
    evidence_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engagement: Mapped[Engagement] = relationship("Engagement")
    modifications: Mapped[list[ScenarioModification]] = relationship(
        "ScenarioModification", back_populates="scenario", cascade="all, delete-orphan"
    )

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


class ScenarioModification(Base):
    """A modification applied to a simulation scenario."""

    __tablename__ = "scenario_modifications"
    __table_args__ = (Index("ix_scenario_modifications_scenario_id", "scenario_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    modification_type: Mapped[ModificationType] = mapped_column(Enum(ModificationType), nullable=False)
    element_id: Mapped[str] = mapped_column(String(512), nullable=False)
    element_name: Mapped[str] = mapped_column(String(512), nullable=False)
    change_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    template_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    scenario: Mapped[SimulationScenario] = relationship("SimulationScenario", back_populates="modifications")

    def __repr__(self) -> str:
        return f"<ScenarioModification(id={self.id}, type={self.modification_type}, element='{self.element_name}')>"


class EpistemicAction(Base):
    """A ranked evidence gap action for epistemic planning."""

    __tablename__ = "epistemic_actions"
    __table_args__ = (Index("ix_epistemic_actions_scenario_id", "scenario_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    target_element_id: Mapped[str] = mapped_column(String(512), nullable=False)
    target_element_name: Mapped[str] = mapped_column(String(512), nullable=False)
    evidence_gap_description: Mapped[str] = mapped_column(Text, nullable=False)
    current_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_confidence_uplift: Mapped[float] = mapped_column(Float, nullable=False)
    projected_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    information_gain_score: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_evidence_category: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    shelf_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shelf_data_requests.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    scenario: Mapped[SimulationScenario] = relationship("SimulationScenario")

    def __repr__(self) -> str:
        return (
            f"<EpistemicAction(id={self.id}, element='{self.target_element_name}', gain={self.information_gain_score})>"
        )


# =============================================================================
# Phase 4: Financial Assumptions & Alternative Suggestions
# =============================================================================


class FinancialAssumptionType(enum.StrEnum):
    """Types of financial assumptions."""

    COST_PER_ROLE = "cost_per_role"
    TECHNOLOGY_COST = "technology_cost"
    VOLUME_FORECAST = "volume_forecast"
    IMPLEMENTATION_COST = "implementation_cost"


class SuggestionDisposition(enum.StrEnum):
    """Disposition states for alternative suggestions."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    MODIFIED = "modified"
    REJECTED = "rejected"


class FinancialAssumption(Base):
    """A financial assumption for scenario cost modelling."""

    __tablename__ = "financial_assumptions"
    __table_args__ = (Index("ix_financial_assumptions_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    assumption_type: Mapped[FinancialAssumptionType] = mapped_column(Enum(FinancialAssumptionType), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<FinancialAssumption(id={self.id}, name='{self.name}', type={self.assumption_type})>"


class AlternativeSuggestion(Base):
    """An LLM-generated alternative scenario suggestion."""

    __tablename__ = "alternative_suggestions"
    __table_args__ = (
        Index("ix_alternative_suggestions_scenario_id", "scenario_id"),
        Index("ix_alternative_suggestions_engagement_id", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=True
    )
    suggestion_text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    governance_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_gaps: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    disposition: Mapped[SuggestionDisposition] = mapped_column(
        Enum(SuggestionDisposition), default=SuggestionDisposition.PENDING, nullable=False
    )
    disposition_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    llm_response: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    scenario: Mapped[SimulationScenario] = relationship("SimulationScenario")

    def __repr__(self) -> str:
        return f"<AlternativeSuggestion(id={self.id}, disposition={self.disposition})>"


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


class CopilotMessage(Base):
    """Persisted copilot chat message for conversation history."""

    __tablename__ = "copilot_messages"
    __table_args__ = (
        Index("ix_copilot_messages_engagement_id", "engagement_id"),
        Index("ix_copilot_messages_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    citations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    context_tokens_used: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<CopilotMessage(id={self.id}, role='{self.role}')>"


# =============================================================================
# Data Layer Evolution: Evidence Lineage & Data Catalog
# =============================================================================


class DataLayer(enum.StrEnum):
    """Medallion architecture layers for data catalog entries."""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class DataClassification(enum.StrEnum):
    """Data sensitivity classification levels."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class EvidenceLineage(Base):
    """Tracks the provenance and transformation history of evidence.

    Records where evidence came from (source system, URL), how it was
    transformed through the pipeline, and supports versioning for
    incremental refresh scenarios.
    """

    __tablename__ = "evidence_lineage"
    __table_args__ = (
        Index("ix_evidence_lineage_evidence_item_id", "evidence_item_id"),
        Index("ix_evidence_lineage_source_system", "source_system"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False
    )
    source_system: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_identifier: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    transformation_chain: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        default=list,
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    version_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_lineage.id", ondelete="SET NULL"), nullable=True
    )
    refresh_schedule: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    evidence_item: Mapped[EvidenceItem] = relationship("EvidenceItem")

    def __repr__(self) -> str:
        return f"<EvidenceLineage(id={self.id}, source='{self.source_system}', version={self.version})>"


class DataCatalogEntry(Base):
    """A dataset entry in the data governance catalog.

    Tracks datasets across medallion layers (bronze/silver/gold), their
    owners, classification, quality SLAs, and retention policies. Designed
    to be portable for client deployment.
    """

    __tablename__ = "data_catalog_entries"
    __table_args__ = (
        Index("ix_data_catalog_entries_layer", "layer"),
        Index("ix_data_catalog_entries_engagement_id", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=True,
    )
    dataset_name: Mapped[str] = mapped_column(String(512), nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(100), nullable=False)
    layer: Mapped[DataLayer] = mapped_column(Enum(DataLayer), nullable=False)
    schema_definition: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classification: Mapped[DataClassification] = mapped_column(
        Enum(DataClassification), default=DataClassification.INTERNAL, nullable=False
    )
    quality_sla: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    retention_days: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    delta_table_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<DataCatalogEntry(id={self.id}, name='{self.dataset_name}', layer={self.layer})>"


# =============================================================================
# Audit: HTTP request audit events (no engagement FK)
# =============================================================================


class HttpAuditEvent(Base):
    """HTTP request audit events for compliance (no engagement FK required).

    Stores all mutating HTTP requests without requiring a valid engagement
    foreign key, enabling audit logging for requests that are not tied to
    a specific engagement (e.g. login, user creation).
    """

    __tablename__ = "http_audit_events"
    __table_args__ = (
        Index("ix_http_audit_events_user_id", "user_id"),
        Index("ix_http_audit_events_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, default="anonymous")
    status_code: Mapped[int] = mapped_column(nullable=False)
    engagement_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # No FK - just string reference
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<HttpAuditEvent(id={self.id}, method='{self.method}', path='{self.path}', user='{self.user_id}')>"
