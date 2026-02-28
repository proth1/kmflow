"""UpliftProjection model for tracking evidence gap confidence uplift predictions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.core.models.engagement import Engagement


class UpliftProjection(Base):
    """Tracks projected vs actual confidence uplift for evidence gap ranking.

    Stores the predicted confidence increase from obtaining specific evidence
    for a given activity. Once evidence is actually obtained, actual_uplift
    is populated to calibrate the projection model over time.
    """

    __tablename__ = "uplift_projections"
    __table_args__ = (
        Index("ix_uplift_projections_engagement_id", "engagement_id"),
        Index("ix_uplift_projections_element_id", "element_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    element_id: Mapped[str] = mapped_column(String(512), nullable=False)
    element_name: Mapped[str] = mapped_column(String(512), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(255), nullable=False)
    current_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    projected_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    projected_uplift: Mapped[float] = mapped_column(Float, nullable=False)
    actual_uplift: Mapped[float | None] = mapped_column(Float, nullable=True)
    brightness: Mapped[str] = mapped_column(String(50), nullable=False)
    projected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    engagement: Mapped[Engagement] = relationship("Engagement")  # noqa: F821 — forward ref

    def __repr__(self) -> str:
        return (
            f"<UpliftProjection(id={self.id}, element='{self.element_name}', "
            f"projected={self.projected_uplift}, actual={self.actual_uplift})>"
        )
