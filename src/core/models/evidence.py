"""Evidence models: category/validation enums, EvidenceItem, EvidenceFragment, EvidenceLineage, DataCatalogEntry."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Date, DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


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


class EvidenceItem(Base):
    """An individual piece of evidence collected during an engagement."""

    __tablename__ = "evidence_items"
    __table_args__ = (Index("ix_evidence_engagement_category", "engagement_id", "category"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[EvidenceCategory] = mapped_column(Enum(EvidenceCategory, values_callable=lambda e: [x.value for x in e]), nullable=False)
    format: Mapped[str] = mapped_column(String(50), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # File storage fields
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Metadata
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extracted_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
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
        Enum(ValidationStatus, values_callable=lambda e: [x.value for x in e]), default=ValidationStatus.PENDING, nullable=False
    )

    # Data sensitivity classification — defaults to INTERNAL
    classification: Mapped[DataClassification] = mapped_column(
        Enum(DataClassification, values_callable=lambda e: [x.value for x in e]), default=DataClassification.INTERNAL, server_default="internal", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    engagement: Mapped["Engagement"] = relationship("Engagement", back_populates="evidence_items")
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
    fragment_type: Mapped[FragmentType] = mapped_column(Enum(FragmentType, values_callable=lambda e: [x.value for x in e]), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    evidence_item: Mapped[EvidenceItem] = relationship("EvidenceItem", back_populates="fragments")

    def __repr__(self) -> str:
        return f"<EvidenceFragment(id={self.id}, type={self.fragment_type})>"


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
    layer: Mapped[DataLayer] = mapped_column(Enum(DataLayer, values_callable=lambda e: [x.value for x in e]), nullable=False)
    schema_definition: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classification: Mapped[DataClassification] = mapped_column(
        Enum(DataClassification, values_callable=lambda e: [x.value for x in e]), default=DataClassification.INTERNAL, nullable=False
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
