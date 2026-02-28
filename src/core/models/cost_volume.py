"""Cost-per-role and volume forecast models (Story #359).

RoleRateAssumption captures hourly/annual rates per role with variance.
VolumeForecast captures baseline transaction volumes with seasonal patterns.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.core.models.engagement import Engagement


class RoleRateAssumption(Base):
    """Hourly and annual rate assumption for a role within an engagement."""

    __tablename__ = "role_rate_assumptions"
    __table_args__ = (
        Index("ix_role_rate_assumptions_engagement_id", "engagement_id"),
        UniqueConstraint("engagement_id", "role_name", name="uq_role_rate_engagement_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    role_name: Mapped[str] = mapped_column(String(256), nullable=False)
    hourly_rate: Mapped[float] = mapped_column(Float, nullable=False)
    annual_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    rate_variance_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<RoleRateAssumption(id={self.id}, role='{self.role_name}', rate={self.hourly_rate})>"


class VolumeForecast(Base):
    """Transaction volume forecast with seasonal adjustment factors."""

    __tablename__ = "volume_forecasts"
    __table_args__ = (Index("ix_volume_forecasts_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    baseline_volume: Mapped[int] = mapped_column(Integer, nullable=False)
    variance_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    seasonal_factors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<VolumeForecast(id={self.id}, name='{self.name}', baseline={self.baseline_volume})>"
