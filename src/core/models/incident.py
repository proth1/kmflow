"""Incident response models for security incident lifecycle management."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

# GDPR Art. 33: 72 hours for supervisory authority notification
GDPR_NOTIFICATION_HOURS = 72
# Escalation trigger: alert DPO at 48 hours (24 hours before deadline)
ESCALATION_THRESHOLD_HOURS = 48


class IncidentClassification(enum.StrEnum):
    """Incident classification per PRD Section 9.6."""

    P1 = "P1"  # Data breach
    P2 = "P2"  # Security incident, no breach
    P3 = "P3"  # Vulnerability
    P4 = "P4"  # Policy violation


class IncidentStatus(enum.StrEnum):
    """Incident lifecycle states."""

    OPEN = "open"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IncidentEventType(enum.StrEnum):
    """Types of events in an incident timeline."""

    CREATED = "created"
    CONTAINMENT_STARTED = "containment_started"
    ACCESS_RESTRICTED = "access_restricted"
    AUDIT_FROZEN = "audit_frozen"
    ESCALATION_SENT = "escalation_sent"
    NOTIFICATION_SENT = "notification_sent"
    RESOLVED = "resolved"
    CLOSED = "closed"
    NOTE_ADDED = "note_added"


class Incident(Base):
    """A security incident with lifecycle tracking and GDPR deadline management."""

    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_engagement_id", "engagement_id"),
        Index("ix_incidents_classification", "classification"),
        Index("ix_incidents_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    classification: Mapped[IncidentClassification] = mapped_column(
        Enum(IncidentClassification, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, values_callable=lambda e: [x.value for x in e]),
        default=IncidentStatus.OPEN,
        nullable=False,
        server_default="open",
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reported_by: Mapped[str] = mapped_column(String(255), nullable=False)
    notification_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeline_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    contained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    events: Mapped[list[IncidentEvent]] = relationship(
        "IncidentEvent", back_populates="incident", cascade="all, delete-orphan", order_by="IncidentEvent.created_at"
    )

    @property
    def hours_until_deadline(self) -> float | None:
        """Hours remaining until GDPR notification deadline."""
        if self.notification_deadline is None:
            return None
        from datetime import UTC

        delta = self.notification_deadline - datetime.now(UTC)
        return max(0.0, delta.total_seconds() / 3600)

    @property
    def needs_escalation(self) -> bool:
        """Whether this incident has passed the escalation threshold."""
        if self.notification_deadline is None or self.status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
            return False
        hours = self.hours_until_deadline
        return hours is not None and hours <= (GDPR_NOTIFICATION_HOURS - ESCALATION_THRESHOLD_HOURS)

    def __repr__(self) -> str:
        return f"<Incident(id={self.id}, classification={self.classification}, status={self.status})>"


class IncidentEvent(Base):
    """An event in an incident's timeline."""

    __tablename__ = "incident_events"
    __table_args__ = (
        Index("ix_incident_events_incident_id", "incident_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[IncidentEventType] = mapped_column(
        Enum(IncidentEventType, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    incident: Mapped[Incident] = relationship("Incident", back_populates="events")

    def __repr__(self) -> str:
        return f"<IncidentEvent(id={self.id}, type={self.event_type})>"
