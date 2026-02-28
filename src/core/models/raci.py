"""RACI matrix models: assignment enums and RACICell persistence (Story #351).

A RACI cell represents a single activity-role intersection in the matrix.
Cells begin in 'proposed' status after auto-derivation from the knowledge graph
and transition to 'validated' upon SME confirmation.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.core.models.engagement import Engagement


class RACIAssignment(enum.StrEnum):
    """RACI responsibility assignment types."""

    RESPONSIBLE = "R"
    ACCOUNTABLE = "A"
    CONSULTED = "C"
    INFORMED = "I"


class RACIStatus(enum.StrEnum):
    """Lifecycle status of a RACI cell."""

    PROPOSED = "proposed"
    VALIDATED = "validated"


class RACICell(Base):
    """A single cell in the RACI matrix linking an activity to a role.

    Auto-derived from PERFORMED_BY/GOVERNED_BY/NOTIFIED_BY/REVIEWS edges
    in the knowledge graph. Each cell tracks its derivation confidence and
    SME validation status.
    """

    __tablename__ = "raci_cells"
    __table_args__ = (
        UniqueConstraint("engagement_id", "activity_id", "role_id", name="uq_raci_cell"),
        Index("ix_raci_cells_engagement_id", "engagement_id"),
        Index("ix_raci_cells_activity_id", "activity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    activity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    activity_name: Mapped[str] = mapped_column(String(512), nullable=False)
    role_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role_name: Mapped[str] = mapped_column(String(512), nullable=False)
    assignment: Mapped[str] = mapped_column(String(1), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="proposed", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, server_default="1.0", nullable=False)
    source_edge_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    validator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    engagement: Mapped["Engagement"] = relationship("Engagement")  # noqa: F821, UP037

    def __repr__(self) -> str:
        return f"<RACICell(id={self.id}, activity='{self.activity_name}', role='{self.role_name}', assignment='{self.assignment}')>"
