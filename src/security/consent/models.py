"""Consent models for desktop endpoint capture (Story #382).

Platform-level consent records for Phase 3 desktop capture. Supports three
consent modes: OPT_IN (individual consent), ORG_AUTHORIZED (organization-level),
and HYBRID (org-authorized with individual opt-out right).

Each consent record links to the policy bundle version in effect at consent time.
Records are immutable after creation — withdrawal creates a separate status update.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class EndpointConsentType(enum.StrEnum):
    """Consent mode for desktop endpoint capture."""

    OPT_IN = "opt_in"
    ORG_AUTHORIZED = "org_authorized"
    HYBRID = "hybrid"


class ConsentStatus(enum.StrEnum):
    """Current state of a consent record."""

    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


class PolicyBundle(Base):
    """Version-controlled policy bundle for consent context.

    Records the specific policy version in effect when consent was given.
    Retained for 7 years per PRD Section 9.8.
    """

    __tablename__ = "policy_bundles"
    __table_args__ = (
        Index("ix_policy_bundles_engagement_id", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    scope: Mapped[str] = mapped_column(
        String(512), nullable=False, default="application-usage-monitoring"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<PolicyBundle(id={self.id}, version={self.version}, scope={self.scope})>"


class EndpointConsentRecord(Base):
    """Immutable consent record for desktop endpoint capture.

    One row per consent grant. Withdrawal updates status to WITHDRAWN
    and records withdrawn_at timestamp. No other mutations are permitted.
    7-year retention floor enforced per PRD Section 9.8.
    """

    __tablename__ = "endpoint_consent_records"
    __table_args__ = (
        Index("ix_endpoint_consent_records_participant_id", "participant_id"),
        Index("ix_endpoint_consent_records_engagement_id", "engagement_id"),
        Index("ix_endpoint_consent_records_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="RESTRICT"),
        nullable=False,
    )
    consent_type: Mapped[EndpointConsentType] = mapped_column(
        Enum(EndpointConsentType), nullable=False
    )
    scope: Mapped[str] = mapped_column(
        String(512), nullable=False, default="application-usage-monitoring"
    )
    policy_bundle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policy_bundles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[ConsentStatus] = mapped_column(
        Enum(ConsentStatus), nullable=False, default=ConsentStatus.ACTIVE
    )
    recorded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # 7-year retention floor (earliest allowed deletion date)
    retention_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<EndpointConsentRecord(id={self.id}, participant={self.participant_id}, "
            f"type={self.consent_type}, status={self.status})>"
        )
