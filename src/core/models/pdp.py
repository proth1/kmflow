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
    # ABAC-specific obligations
    MASK_FIELDS = "mask_fields"
    SUPPRESS_COHORT = "suppress_cohort"
    ENFORCE_FIELD_ALLOWLIST = "enforce_field_allowlist"
    APPLY_RETENTION_LIMIT = "apply_retention_limit"


class OperationType(enum.StrEnum):
    """Types of operations the PDP evaluates."""

    READ = "read"
    WRITE = "write"
    EXPORT = "export"
    DELETE = "delete"


class PDPPolicyBundle(Base):
    """Versioned container for a set of PDP policy rules.

    Agents reference a bundle version in heartbeats so the PDP can detect
    version drift and force re-evaluation when policies change.

    Note: This is distinct from src.security.consent.models.PolicyBundle,
    which tracks consent-related policy versions per engagement.
    """

    __tablename__ = "pdp_policy_bundles"
    __table_args__ = (
        Index("ix_pdp_policy_bundles_active", "is_active"),
        Index("ix_pdp_policy_bundles_version", "version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<PDPPolicyBundle(id={self.id}, version={self.version}, is_active={self.is_active})>"


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


class PolicyObligation(Base):
    """Structured obligation record linked to a specific policy rule.

    Separates obligation definitions from the inline obligations_json on PDPPolicy,
    enabling richer obligation management including enforcement_point tracking.

    conditions_json ABAC attributes supported:
      - department: str — e.g. "finance", "hr"
      - cost_center: str — e.g. "CC-1001"
      - data_residency: str — e.g. "EU", "US"
      - cohort_size: int — minimum cohort for aggregated data
      - evidence_type: str — e.g. "interview", "document"
      - identity_posture: str — e.g. "managed", "unmanaged"
      - export_mode: str — e.g. "csv", "pdf"
    """

    __tablename__ = "policy_obligations"
    __table_args__ = (
        Index("ix_policy_obligations_policy_id", "policy_id"),
        Index("ix_policy_obligations_type", "obligation_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pdp_policies.id", ondelete="CASCADE"), nullable=False
    )
    obligation_type: Mapped[ObligationType] = mapped_column(
        Enum(ObligationType, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    # Parameters for the obligation handler: {"fields": ["ssn", "dob"], "min_cohort": 5}
    parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Where enforcement occurs: "response", "request", "export"
    enforcement_point: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<PolicyObligation(id={self.id}, type={self.obligation_type}, policy_id={self.policy_id})>"


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
