"""Assessment Overlay Matrix model.

Stores process area assessments on a 2D matrix:
- X-axis: Ability to Execute (0-100) — composite of maturity, evidence confidence, compliance
- Y-axis: Value (0-100) — composite of volume impact, cost savings potential, risk reduction

Each entry represents one process area within an engagement's assessment.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.core.models.engagement import Engagement


class Quadrant(enum.StrEnum):
    """Quadrant classification based on Value and Ability-to-Execute axes."""

    TRANSFORM = "transform"  # High value, high ability — prioritize
    INVEST = "invest"  # High value, low ability — invest to build capability
    MAINTAIN = "maintain"  # Low value, high ability — maintain current state
    DEPRIORITIZE = "deprioritize"  # Low value, low ability — lowest priority


class AssessmentMatrixEntry(Base):
    """A single process area plotted on the Assessment Overlay Matrix."""

    __tablename__ = "assessment_matrix_entries"
    __table_args__ = (
        Index("ix_assessment_matrix_entries_engagement_id", "engagement_id"),
        UniqueConstraint("engagement_id", "process_area_name", name="uq_assessment_matrix_area"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )

    process_area_name: Mapped[str] = mapped_column(String(512), nullable=False)
    process_area_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # X-axis: Ability to Execute (0-100)
    ability_to_execute: Mapped[float] = mapped_column(Float, nullable=False)
    ability_components: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Y-axis: Value (0-100)
    value_score: Mapped[float] = mapped_column(Float, nullable=False)
    value_components: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Derived quadrant
    quadrant: Mapped[Quadrant] = mapped_column(
        Enum(Quadrant, values_callable=lambda e: [x.value for x in e]), nullable=False
    )

    # Metadata
    element_count: Mapped[int] = mapped_column(default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<AssessmentMatrixEntry(id={self.id}, area='{self.process_area_name}', quadrant={self.quadrant})>"
