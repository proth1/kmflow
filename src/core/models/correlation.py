"""CaseLinkEdge model for correlation engine results.

Records the linkage between a canonical activity event and a business case/ticket,
capturing the method used (deterministic, assisted, role_aggregate) and an
explainability vector that shows which features drove the link score.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class CaseLinkEdge(Base):
    """A resolved link between a canonical event and a business case.

    Created by the correlation engine (deterministic or assisted pass).
    method='role_aggregate' is used when an event cannot be linked to a
    specific case but is attributed to a role cohort.
    """

    __tablename__ = "case_link_edges"
    __table_args__ = (
        Index("ix_case_links_engagement", "engagement_id"),
        Index("ix_case_links_case_id", "case_id"),
        Index("ix_case_links_event_id", "event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_activity_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    explainability: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<CaseLinkEdge(id={self.id}, event_id={self.event_id}, "
            f"case_id='{self.case_id}', method='{self.method}', confidence={self.confidence:.2f})>"
        )
