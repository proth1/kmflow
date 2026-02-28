"""Policy Decision Point (PDP) models per PRD Section 9.9."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class PDPDecisionType(enum.StrEnum):
    """PDP evaluation outcome."""

    PERMIT = "permit"
    DENY = "deny"


class ObligationType(enum.StrEnum):
    """Obligations that may be attached to a PERMIT decision."""

    APPLY_WATERMARK = "apply_watermark"
    LOG_ENHANCED_AUDIT = "log_enhanced_audit"
    REQUIRE_MFA = "require_mfa"
    REDACT_FIELDS = "redact_fields"


class OperationType(enum.StrEnum):
    """Types of operations the PDP evaluates."""

    READ = "read"
    WRITE = "write"
    EXPORT = "export"
    DELETE = "delete"


class PDPPolicy(Base):
    """A policy rule evaluated by the PDP service."""

    __tablename__ = "pdp_policies"
    __table_args__ = (
        Index("ix_pdp_policies_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Conditions (JSON): {"classification": "restricted", "operation": "read", "min_role": "engagement_lead"}
    conditions_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Decision to render when conditions match
    decision: Mapped[PDPDecisionType] = mapped_column(
        Enum(PDPDecisionType, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    # Obligations (JSON list): [{"type": "apply_watermark", "params": {"recipient_id": true}}]
    obligations_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Priority: lower number = evaluated first
    priority: Mapped[int] = mapped_column(default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<PDPPolicy(id={self.id}, name={self.name}, decision={self.decision})>"


class PDPAuditEntry(Base):
    """Append-only audit trail for PDP decisions."""

    __tablename__ = "pdp_audit_entries"
    __table_args__ = (
        Index("ix_pdp_audit_actor", "actor"),
        Index("ix_pdp_audit_engagement", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[PDPDecisionType] = mapped_column(
        Enum(PDPDecisionType, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    obligations_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<PDPAuditEntry(id={self.id}, decision={self.decision})>"


# Default policy rules for initial deployment
DEFAULT_POLICIES: list[dict] = [
    {
        "name": "deny_restricted_below_lead",
        "description": "Deny access to RESTRICTED data for roles below ENGAGEMENT_LEAD",
        "conditions_json": {
            "classification": "restricted",
            "max_role": "process_analyst",
        },
        "decision": PDPDecisionType.DENY,
        "reason": "insufficient_clearance",
        "priority": 10,
    },
    {
        "name": "watermark_confidential_export",
        "description": "Require watermark when exporting CONFIDENTIAL data",
        "conditions_json": {
            "classification": "confidential",
            "operation": "export",
        },
        "decision": PDPDecisionType.PERMIT,
        "obligations_json": [{"type": "apply_watermark", "params": {"recipient_id": True}}],
        "reason": "export_permitted_with_watermark",
        "priority": 20,
    },
    {
        "name": "enhanced_audit_restricted",
        "description": "Permit RESTRICTED access for authorized roles with enhanced audit",
        "conditions_json": {
            "classification": "restricted",
        },
        "decision": PDPDecisionType.PERMIT,
        "obligations_json": [{"type": "log_enhanced_audit"}],
        "reason": "access_permitted_with_enhanced_audit",
        "priority": 50,
    },
]
