"""POV models: process model enums, ProcessModel, ProcessElement, Contradiction, EvidenceGap."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.core.models.engagement import Engagement


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


class BrightnessClassification(enum.StrEnum):
    """Brightness classification for the three-dimensional confidence model.

    Derived from min(score_brightness, grade_brightness).
    """

    BRIGHT = "bright"
    DIM = "dim"
    DARK = "dark"


class EvidenceGrade(enum.StrEnum):
    """Evidence grade for a process element.

    A = SME-validated + multi-plane corroboration
    B = Multi-source, partially validated
    C = Multiple sources but unvalidated
    D = Single-source unvalidated claim
    U = No evidence (unknown)
    """

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    U = "U"


class GapSeverity(enum.StrEnum):
    """Severity levels for evidence gaps."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProcessModel(Base):
    """A generated Process Point of View model from the consensus algorithm."""

    __tablename__ = "process_models"
    __table_args__ = (Index("ix_process_models_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    scope: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[ProcessModelStatus] = mapped_column(
        Enum(ProcessModelStatus, values_callable=lambda e: [x.value for x in e]),
        default=ProcessModelStatus.GENERATING,
        nullable=False,
    )
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    bpmn_xml: Mapped[str | None] = mapped_column(Text, nullable=True)
    element_count: Mapped[int] = mapped_column(default=0, nullable=False)
    evidence_count: Mapped[int] = mapped_column(default=0, nullable=False)
    contradiction_count: Mapped[int] = mapped_column(default=0, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_by: Mapped[str] = mapped_column(String(255), default="consensus_algorithm", nullable=False)
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
    element_type: Mapped[ProcessElementType] = mapped_column(
        Enum(ProcessElementType, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    triangulation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    corroboration_level: Mapped[CorroborationLevel] = mapped_column(
        Enum(CorroborationLevel, values_callable=lambda e: [x.value for x in e]),
        default=CorroborationLevel.WEAKLY,
        nullable=False,
    )
    evidence_count: Mapped[int] = mapped_column(default=0, nullable=False)
    evidence_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    evidence_grade: Mapped[EvidenceGrade] = mapped_column(
        Enum(EvidenceGrade, values_callable=lambda e: [x.value for x in e]),
        default=EvidenceGrade.U,
        nullable=False,
    )
    brightness_classification: Mapped[BrightnessClassification] = mapped_column(
        Enum(BrightnessClassification, values_callable=lambda e: [x.value for x in e]),
        default=BrightnessClassification.DARK,
        nullable=False,
    )
    mvc_threshold_passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    gap_type: Mapped[GapType] = mapped_column(
        Enum(GapType, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[GapSeverity] = mapped_column(
        Enum(GapSeverity, values_callable=lambda e: [x.value for x in e]), default=GapSeverity.MEDIUM, nullable=False
    )
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_element_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_elements.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    process_model: Mapped[ProcessModel] = relationship("ProcessModel", back_populates="evidence_gaps")

    def __repr__(self) -> str:
        return f"<EvidenceGap(id={self.id}, type={self.gap_type}, severity={self.severity})>"
