"""Conformance models: ReferenceProcessModel, ConformanceResult."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.core.models.engagement import Engagement


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
        Index("ix_conformance_results_pov_model_id", "pov_model_id"),
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
