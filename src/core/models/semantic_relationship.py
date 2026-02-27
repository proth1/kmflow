"""SemanticRelationship model with bitemporal validity tracking.

Implements PRD v2.1 Section 6.2 (Semantic Relationship Engine, Bitemporal
Validity table) and Section 6.3 (Three-Way Distinction, TEMPORAL_SHIFT
resolution path).

Bitemporal properties enable:
- Point-in-time queries ("what was believed true at time T?")
- Assertion lifecycle tracking (asserted → retracted → superseded)
- TEMPORAL_SHIFT conflict resolution via valid_from/valid_to windows
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class SemanticRelationship(Base):
    """A semantic relationship between two graph nodes with bitemporal validity.

    Stored in both PostgreSQL (this model) and Neo4j (graph properties).
    The five bitemporal columns track two timelines:
    - Transaction time: asserted_at / retracted_at (when the system recorded it)
    - Valid time: valid_from / valid_to (when the fact holds in the real world)
    - superseded_by links to the replacing assertion.
    """

    __tablename__ = "semantic_relationships"
    __table_args__ = (
        Index("ix_semantic_relationships_engagement_id", "engagement_id"),
        Index("ix_semantic_relationships_source_node_id", "source_node_id"),
        Index("ix_semantic_relationships_target_node_id", "target_node_id"),
        Index("ix_semantic_relationships_retracted_at", "retracted_at"),
        Index("ix_semantic_relationships_edge_type", "edge_type"),
        Index("ix_semantic_relationships_superseded_by", "superseded_by"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    source_node_id: Mapped[str] = mapped_column(String(500), nullable=False)
    target_node_id: Mapped[str] = mapped_column(String(500), nullable=False)
    edge_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # Bitemporal validity properties
    asserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    retracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("semantic_relationships.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<SemanticRelationship(id={self.id}, "
            f"{self.source_node_id}-[{self.edge_type}]->{self.target_node_id}, "
            f"retracted={'yes' if self.retracted_at else 'no'})>"
        )
