"""TOM models: dimension/gap/maturity enums, TargetOperatingModel, GapAnalysisResult, BestPractice, Benchmark."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
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
    gap_type: Mapped[TOMGapType] = mapped_column(Enum(TOMGapType, values_callable=lambda e: [x.value for x in e]), nullable=False)
    dimension: Mapped[TOMDimension] = mapped_column(Enum(TOMDimension, values_callable=lambda e: [x.value for x in e]), nullable=False)
    severity: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    engagement: Mapped["Engagement"] = relationship("Engagement")
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
