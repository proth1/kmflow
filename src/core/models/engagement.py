"""Engagement models: status enums, Engagement, ShelfDataRequest, ShelfDataRequestItem."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Date, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base
from src.core.models.evidence import EvidenceCategory


class EngagementStatus(enum.StrEnum):
    """Status values for an engagement."""

    DRAFT = "draft"
    ACTIVE = "active"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ShelfRequestStatus(enum.StrEnum):
    """Status values for a shelf data request."""

    DRAFT = "draft"
    SENT = "sent"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"


class ShelfRequestItemStatus(enum.StrEnum):
    """Status values for a shelf data request item."""

    PENDING = "pending"
    RECEIVED = "received"
    OVERDUE = "overdue"


class ShelfRequestItemPriority(enum.StrEnum):
    """Priority values for a shelf data request item."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Engagement(Base):
    """A consulting engagement scope."""

    __tablename__ = "engagements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client: Mapped[str] = mapped_column(String(255), nullable=False)
    business_area: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EngagementStatus] = mapped_column(
        Enum(EngagementStatus), default=EngagementStatus.DRAFT, nullable=False
    )
    team: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    retention_days: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=365)  # 365-day default satisfies data minimization; None = indefinite (not recommended)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    evidence_items: Mapped[list["EvidenceItem"]] = relationship(
        "EvidenceItem", back_populates="engagement", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="engagement", passive_deletes=True
    )
    shelf_data_requests: Mapped[list["ShelfDataRequest"]] = relationship(
        "ShelfDataRequest", back_populates="engagement", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Engagement(id={self.id}, name='{self.name}', client='{self.client}')>"


class ShelfDataRequest(Base):
    """A shelf data request sent to a client to gather evidence."""

    __tablename__ = "shelf_data_requests"
    __table_args__ = (Index("ix_shelf_requests_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ShelfRequestStatus] = mapped_column(
        Enum(ShelfRequestStatus), default=ShelfRequestStatus.DRAFT, nullable=False
    )
    due_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement", back_populates="shelf_data_requests")
    items: Mapped[list["ShelfDataRequestItem"]] = relationship(
        "ShelfDataRequestItem", back_populates="request", cascade="all, delete-orphan"
    )

    @property
    def fulfillment_percentage(self) -> float:
        """Calculate the percentage of items that have been received."""
        if not self.items:
            return 0.0
        received = sum(1 for item in self.items if item.status == ShelfRequestItemStatus.RECEIVED)
        return round(received / len(self.items) * 100.0, 2)

    def __repr__(self) -> str:
        return f"<ShelfDataRequest(id={self.id}, title='{self.title}', status={self.status})>"


class ShelfDataRequestItem(Base):
    """An individual item requested within a shelf data request."""

    __tablename__ = "shelf_data_request_items"
    __table_args__ = (Index("ix_shelf_request_items_request_id", "request_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shelf_data_requests.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[EvidenceCategory] = mapped_column(Enum(EvidenceCategory), nullable=False)
    item_name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[ShelfRequestItemPriority] = mapped_column(
        Enum(ShelfRequestItemPriority), default=ShelfRequestItemPriority.MEDIUM, nullable=False
    )
    status: Mapped[ShelfRequestItemStatus] = mapped_column(
        Enum(ShelfRequestItemStatus), default=ShelfRequestItemStatus.PENDING, nullable=False
    )
    matched_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    request: Mapped[ShelfDataRequest] = relationship("ShelfDataRequest", back_populates="items")

    def __repr__(self) -> str:
        return f"<ShelfDataRequestItem(id={self.id}, name='{self.item_name}', status={self.status})>"
