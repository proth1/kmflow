"""TOM models: dimension/gap/maturity enums, TargetOperatingModel, GapAnalysisResult, BestPractice, Benchmark, TransformationRoadmap."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


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


class TargetOperatingModel(Base):
    """A Target Operating Model definition for an engagement."""

    __tablename__ = "target_operating_models"
    __table_args__ = (Index("ix_tom_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    dimensions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    maturity_targets: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    engagement: Mapped["Engagement"] = relationship("Engagement")
    gap_results: Mapped[list[GapAnalysisResult]] = relationship(
        "GapAnalysisResult", back_populates="tom", cascade="all, delete-orphan"
    )
    dimension_records: Mapped[list[TOMDimensionRecord]] = relationship(
        "TOMDimensionRecord", back_populates="tom", cascade="all, delete-orphan", order_by="TOMDimensionRecord.dimension_type"
    )
    versions: Mapped[list[TOMVersion]] = relationship(
        "TOMVersion", back_populates="tom", cascade="all, delete-orphan", order_by="TOMVersion.version_number"
    )

    def __repr__(self) -> str:
        return f"<TargetOperatingModel(id={self.id}, name='{self.name}', version={self.version})>"


class TOMDimensionRecord(Base):
    """A structured dimension record for a TOM."""

    __tablename__ = "tom_dimensions"
    __table_args__ = (
        Index("ix_tom_dimensions_tom_id", "tom_id"),
        UniqueConstraint("tom_id", "dimension_type", name="uq_tom_dimension_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("target_operating_models.id", ondelete="CASCADE"), nullable=False
    )
    dimension_type: Mapped[TOMDimension] = mapped_column(
        Enum(TOMDimension, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    maturity_target: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    tom: Mapped[TargetOperatingModel] = relationship("TargetOperatingModel", back_populates="dimension_records")

    def __repr__(self) -> str:
        return f"<TOMDimensionRecord(tom_id={self.tom_id}, type={self.dimension_type}, target={self.maturity_target})>"


class TOMVersion(Base):
    """A version snapshot of a TOM, created on each update."""

    __tablename__ = "tom_versions"
    __table_args__ = (
        Index("ix_tom_versions_tom_id", "tom_id"),
        UniqueConstraint("tom_id", "version_number", name="uq_tom_version_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("target_operating_models.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    tom: Mapped[TargetOperatingModel] = relationship("TargetOperatingModel", back_populates="versions")

    def __repr__(self) -> str:
        return f"<TOMVersion(tom_id={self.tom_id}, version={self.version_number})>"


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
    gap_type: Mapped[TOMGapType] = mapped_column(Enum(TOMGapType, values_callable=lambda e: [x.value for x in e]), nullable=False)
    dimension: Mapped[TOMDimension] = mapped_column(Enum(TOMDimension, values_callable=lambda e: [x.value for x in e]), nullable=False)
    severity: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    depends_on_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    engagement: Mapped["Engagement"] = relationship("Engagement")
    tom: Mapped[TargetOperatingModel] = relationship("TargetOperatingModel", back_populates="gap_results")

    @property
    def priority_score(self) -> float:
        """Computed priority: severity * confidence."""
        return round(self.severity * self.confidence, 4)

    @property
    def effort_weeks(self) -> float:
        """Effort estimate in weeks derived from remediation_cost (1-5 scale)."""
        cost_map = {1: 0.5, 2: 1.0, 3: 2.0, 4: 4.0, 5: 8.0}
        return cost_map.get(self.remediation_cost or 3, 2.0)

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
    tom_dimension: Mapped[TOMDimension] = mapped_column(Enum(TOMDimension, values_callable=lambda e: [x.value for x in e]), nullable=False)
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


class RoadmapStatus(enum.StrEnum):
    """Transformation roadmap status."""

    DRAFT = "draft"
    FINAL = "final"


class TransformationRoadmapModel(Base):
    """A persisted transformation roadmap generated from gap analysis."""

    __tablename__ = "transformation_roadmaps"
    __table_args__ = (
        Index("ix_transformation_roadmaps_engagement_id", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[RoadmapStatus] = mapped_column(
        Enum(RoadmapStatus, values_callable=lambda e: [x.value for x in e]),
        default=RoadmapStatus.DRAFT,
        nullable=False,
    )
    phases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    total_initiatives: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_duration_weeks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    engagement: Mapped["Engagement"] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<TransformationRoadmapModel(id={self.id}, status={self.status})>"
