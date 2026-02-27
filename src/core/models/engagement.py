"""Engagement models: status enums, Engagement, ShelfDataRequest, ShelfDataRequestItem, ShelfDataRequestToken."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
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
    """Status values for a shelf data request.

    Lifecycle: DRAFT → OPEN → IN_PROGRESS → COMPLETE → (CANCELLED | OVERDUE)
    Legacy values SENT and COMPLETED are retained for backward compatibility
    with existing database rows. New code should use COMPLETE, not COMPLETED.
    """

    DRAFT = "draft"
    OPEN = "open"
    SENT = "sent"  # Legacy: retained for existing rows
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    COMPLETED = "completed"  # Legacy: use COMPLETE for new records
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


class ShelfRequestItemStatus(enum.StrEnum):
    """Status values for a shelf data request item."""

    PENDING = "pending"
    REQUESTED = "requested"
    RECEIVED = "received"
    VALIDATED = "validated"
    ACTIVE = "active"
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
        Enum(EngagementStatus, values_callable=lambda e: [x.value for x in e]),
        default=EngagementStatus.DRAFT,
        nullable=False,
    )
    team: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    retention_days: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, default=365
    )  # 365-day default satisfies data minimization; None = indefinite (not recommended)
    quality_weights: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=None
    )  # Engagement-level quality scoring weights; None = use system defaults
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    evidence_items: Mapped[list["EvidenceItem"]] = relationship(  # noqa: F821, UP037
        "EvidenceItem", back_populates="engagement", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # noqa: F821, UP037
        "AuditLog", back_populates="engagement", passive_deletes=True
    )
    shelf_data_requests: Mapped[list[ShelfDataRequest]] = relationship(
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
        Enum(ShelfRequestStatus, values_callable=lambda e: [x.value for x in e]),
        default=ShelfRequestStatus.DRAFT,
        nullable=False,
    )
    due_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completion_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement", back_populates="shelf_data_requests")
    items: Mapped[list[ShelfDataRequestItem]] = relationship(
        "ShelfDataRequestItem", back_populates="request", cascade="all, delete-orphan"
    )
    follow_up_reminders: Mapped[list[FollowUpReminder]] = relationship(
        "FollowUpReminder", back_populates="request", cascade="all, delete-orphan"
    )

    @property
    def fulfillment_percentage(self) -> float:
        """Calculate the percentage of items that have been received or beyond."""
        if not self.items:
            return 0.0
        fulfilled_statuses = {
            ShelfRequestItemStatus.RECEIVED,
            ShelfRequestItemStatus.VALIDATED,
            ShelfRequestItemStatus.ACTIVE,
        }
        fulfilled = sum(1 for item in self.items if item.status in fulfilled_statuses)
        return round(fulfilled / len(self.items) * 100.0, 2)

    @property
    def outstanding_items(self) -> list[ShelfDataRequestItem]:
        """Return items that are still REQUESTED or PENDING."""
        outstanding_statuses = {ShelfRequestItemStatus.PENDING, ShelfRequestItemStatus.REQUESTED}
        return [item for item in self.items if item.status in outstanding_statuses]

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
    category: Mapped[EvidenceCategory] = mapped_column(
        Enum(EvidenceCategory, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    item_name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[ShelfRequestItemPriority] = mapped_column(
        Enum(ShelfRequestItemPriority, values_callable=lambda e: [x.value for x in e]),
        default=ShelfRequestItemPriority.MEDIUM,
        nullable=False,
    )
    status: Mapped[ShelfRequestItemStatus] = mapped_column(
        Enum(ShelfRequestItemStatus, values_callable=lambda e: [x.value for x in e]),
        default=ShelfRequestItemStatus.PENDING,
        nullable=False,
    )
    matched_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
    )
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
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


class FollowUpReminder(Base):
    """Automated follow-up reminder for overdue shelf data request items."""

    __tablename__ = "follow_up_reminders"
    __table_args__ = (
        Index("ix_follow_up_reminders_request_id", "request_id"),
        Index("ix_follow_up_reminders_item_id", "item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shelf_data_requests.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shelf_data_request_items.id", ondelete="CASCADE"), nullable=False
    )
    reminder_type: Mapped[str] = mapped_column(String(50), default="overdue", server_default="overdue", nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    request: Mapped[ShelfDataRequest] = relationship("ShelfDataRequest", back_populates="follow_up_reminders")
    item: Mapped[ShelfDataRequestItem] = relationship("ShelfDataRequestItem")

    def __repr__(self) -> str:
        return f"<FollowUpReminder(id={self.id}, item_id={self.item_id}, type={self.reminder_type})>"


class UploadFileStatus(enum.StrEnum):
    """Status values for an individual file in a bulk intake upload."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


class ShelfDataRequestToken(Base):
    """Time-limited intake token for client evidence submission.

    Clients receive a URL containing this token; no authentication is
    required on the client side. The token is validated by expiry
    timestamp before the intake handler processes uploads.
    """

    __tablename__ = "shelf_data_request_tokens"
    __table_args__ = (
        Index("ix_shelf_request_tokens_request_id", "request_id"),
        Index("ix_shelf_request_tokens_token", "token", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shelf_data_requests.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    request: Mapped[ShelfDataRequest] = relationship("ShelfDataRequest")

    @property
    def is_expired(self) -> bool:
        """Check if the token has expired."""

        return datetime.now(UTC) > self.expires_at

    def __repr__(self) -> str:
        return f"<ShelfDataRequestToken(id={self.id}, request_id={self.request_id}, expired={self.is_expired})>"
