"""Cross-border data transfer control models per GDPR requirements."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class DataResidencyRestriction(enum.StrEnum):
    """Engagement-level data residency restriction per PRD Section 9.5."""

    NONE = "none"
    EU_ONLY = "eu_only"
    UK_ONLY = "uk_only"
    CUSTOM = "custom"


class TransferDecision(enum.StrEnum):
    """Result of a transfer control evaluation."""

    PERMITTED = "permitted"
    BLOCKED_NO_TIA = "blocked_no_tia"
    BLOCKED_NO_SCC = "blocked_no_scc"
    BLOCKED_NO_MECHANISM = "blocked_no_mechanism"
    NOT_APPLICABLE = "not_applicable"


class TIAStatus(enum.StrEnum):
    """Transfer Impact Assessment status."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# Jurisdiction registry: maps provider/connector names to jurisdiction codes
JURISDICTION_REGISTRY: dict[str, str] = {
    "anthropic": "US",
    "openai": "US",
    "azure_openai": "EU",
    "aws_bedrock_us": "US",
    "aws_bedrock_eu": "EU",
    "google_vertex_us": "US",
    "google_vertex_eu": "EU",
}

# Restricted jurisdictions per residency type
RESTRICTED_DESTINATIONS: dict[DataResidencyRestriction, set[str]] = {
    DataResidencyRestriction.NONE: set(),  # No restrictions
    DataResidencyRestriction.EU_ONLY: {"US", "CN", "RU", "IN"},  # Block non-adequate countries
    DataResidencyRestriction.UK_ONLY: {"US", "CN", "RU", "IN"},
    DataResidencyRestriction.CUSTOM: set(),  # Custom rules per engagement
}


class TransferImpactAssessment(Base):
    """Transfer Impact Assessment record for cross-border data transfers."""

    __tablename__ = "transfer_impact_assessments"
    __table_args__ = (
        Index("ix_tia_engagement_id", "engagement_id"),
        Index("ix_tia_connector_id", "connector_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    connector_id: Mapped[str] = mapped_column(String(255), nullable=False)
    destination_jurisdiction: Mapped[str] = mapped_column(String(10), nullable=False)
    assessor: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[TIAStatus] = mapped_column(
        Enum(TIAStatus, values_callable=lambda e: [x.value for x in e]),
        default=TIAStatus.PENDING,
        nullable=False,
        server_default="pending",
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<TIA(id={self.id}, connector={self.connector_id}, status={self.status})>"


class StandardContractualClause(Base):
    """SCC record linking an engagement integration to legal mechanism."""

    __tablename__ = "standard_contractual_clauses"
    __table_args__ = (
        Index("ix_scc_engagement_id", "engagement_id"),
        Index("ix_scc_connector_id", "connector_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    connector_id: Mapped[str] = mapped_column(String(255), nullable=False)
    scc_version: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(255), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<SCC(id={self.id}, connector={self.connector_id}, ref={self.reference_id})>"


class DataTransferLog(Base):
    """Append-only log of all permitted data transfers."""

    __tablename__ = "data_transfer_log"
    __table_args__ = (
        Index("ix_dtl_engagement_id", "engagement_id"),
        Index("ix_dtl_connector_id", "connector_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    connector_id: Mapped[str] = mapped_column(String(255), nullable=False)
    destination_jurisdiction: Mapped[str] = mapped_column(String(10), nullable=False)
    decision: Mapped[TransferDecision] = mapped_column(
        Enum(TransferDecision, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    scc_reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tia_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<DataTransferLog(id={self.id}, decision={self.decision})>"
