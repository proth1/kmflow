"""Domain ontology models for engagement-scoped ontology derivation.

Implements KMFLOW-6: Derive domain ontology from knowledge graph.
Models represent a versioned ontology with classes, properties, and axioms
derived from seed terms and Neo4j relationship patterns.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class OntologyStatus(enum.StrEnum):
    """Lifecycle status of an ontology version."""

    DERIVING = "deriving"
    DERIVED = "derived"
    VALIDATED = "validated"
    EXPORTED = "exported"


class OntologyVersion(Base):
    """A versioned ontology derived for an engagement.

    Each derivation run creates a new OntologyVersion with linked classes,
    properties, and axioms. The completeness_score indicates how well the
    ontology covers the engagement's seed term categories.
    """

    __tablename__ = "ontology_versions"
    __table_args__ = (
        Index("ix_ontology_versions_engagement_id", "engagement_id"),
        Index("ix_ontology_versions_engagement_status", "engagement_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[OntologyStatus] = mapped_column(
        Enum(OntologyStatus, values_callable=lambda e: [x.value for x in e]),
        default=OntologyStatus.DERIVING,
        nullable=False,
    )
    completeness_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    class_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    property_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    axiom_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    derived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OntologyClass(Base):
    """An ontology class derived from seed term categories.

    Each class represents a domain concept inferred from clustered seed terms.
    The parent_class_id supports class hierarchy (subsumption).
    """

    __tablename__ = "ontology_classes"
    __table_args__ = (Index("ix_ontology_classes_ontology_id", "ontology_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ontology_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_versions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_class_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_classes.id", ondelete="SET NULL"), nullable=True
    )
    source_seed_terms: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    instance_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OntologyProperty(Base):
    """An ontology property derived from typed edge vocabulary.

    Maps the 12 controlled relationship types from the knowledge graph
    to formal ontology properties with domain and range classes.
    """

    __tablename__ = "ontology_properties"
    __table_args__ = (Index("ix_ontology_properties_ontology_id", "ontology_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ontology_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_versions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    source_edge_type: Mapped[str] = mapped_column(String(100), nullable=False)
    domain_class_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_classes.id", ondelete="SET NULL"), nullable=True
    )
    range_class_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_classes.id", ondelete="SET NULL"), nullable=True
    )
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OntologyAxiom(Base):
    """An ontology axiom derived from validated relationship patterns.

    Axioms represent constraints inferred from frequent, high-confidence
    patterns in the knowledge graph (e.g., "every Activity is PERFORMED_BY
    at least one Role").
    """

    __tablename__ = "ontology_axioms"
    __table_args__ = (Index("ix_ontology_axioms_ontology_id", "ontology_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ontology_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ontology_versions.id", ondelete="CASCADE"), nullable=False
    )
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    axiom_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_pattern: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
