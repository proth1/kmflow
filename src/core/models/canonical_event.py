"""Canonical Activity Event model for the event spine.

Normalizes raw events from heterogeneous source systems into a unified
schema for case timeline assembly and replay visualization.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class EventMappingStatus(enum.StrEnum):
    """Whether the event's activity name was successfully mapped."""

    MAPPED = "mapped"
    UNMAPPED = "unmapped"


class CanonicalActivityEvent(Base):
    """A normalized event from the event spine.

    Events are deduplicated by (case_id, activity_name, timestamp_utc)
    with configurable tolerance, retaining the highest-confidence source.
    """

    __tablename__ = "canonical_activity_events"
    __table_args__ = (
        Index("ix_canonical_events_case_id_ts", "case_id", "timestamp_utc"),
        Index("ix_canonical_events_engagement_id", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(String(255), nullable=False)
    activity_name: Mapped[str] = mapped_column(String(512), nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(255), nullable=False)
    performer_role_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_refs: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    brightness: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mapping_status: Mapped[EventMappingStatus] = mapped_column(
        Enum(EventMappingStatus, values_callable=lambda e: [x.value for x in e]),
        default=EventMappingStatus.MAPPED,
        nullable=False,
    )
    process_element_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<CanonicalActivityEvent(id={self.id}, case_id='{self.case_id}', "
            f"activity='{self.activity_name}', source='{self.source_system}')>"
        )
