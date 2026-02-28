"""Governance models: policy/control enums, Policy, Control, Regulation, ControlEffectivenessScore, ComplianceAssessment, GovernanceGapFinding."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.core.models.engagement import Engagement
    from src.core.models.pov import ProcessElement


class PolicyType(enum.StrEnum):
    """Types of policies that govern processes."""

    ORGANIZATIONAL = "organizational"
    REGULATORY = "regulatory"
    OPERATIONAL = "operational"
    SECURITY = "security"


class ControlEffectiveness(enum.StrEnum):
    """Effectiveness rating for controls."""

    HIGHLY_EFFECTIVE = "highly_effective"
    EFFECTIVE = "effective"
    MODERATELY_EFFECTIVE = "moderately_effective"
    INEFFECTIVE = "ineffective"


class ComplianceLevel(enum.StrEnum):
    """Compliance assessment levels."""

    FULLY_COMPLIANT = "fully_compliant"
    PARTIALLY_COMPLIANT = "partially_compliant"
    NON_COMPLIANT = "non_compliant"
    NOT_ASSESSED = "not_assessed"


class GovernanceGapType(enum.StrEnum):
    """Types of governance gaps from the disagreement taxonomy."""

    CONTROL_GAP = "control_gap"


class GovernanceGapSeverity(enum.StrEnum):
    """Severity of governance gap findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class GovernanceGapStatus(enum.StrEnum):
    """Status of a governance gap finding."""

    OPEN = "open"
    RESOLVED = "resolved"


class Policy(Base):
    """A policy that governs processes within an engagement."""

    __tablename__ = "policies"
    __table_args__ = (Index("ix_policies_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    policy_type: Mapped[PolicyType] = mapped_column(
        Enum(PolicyType, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    source_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
    )
    clauses: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<Policy(id={self.id}, name='{self.name}', type={self.policy_type})>"


class Control(Base):
    """A control that enforces policies within an engagement."""

    __tablename__ = "controls"
    __table_args__ = (Index("ix_controls_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    effectiveness: Mapped[ControlEffectiveness] = mapped_column(
        Enum(ControlEffectiveness, values_callable=lambda e: [x.value for x in e]),
        default=ControlEffectiveness.EFFECTIVE,
        nullable=False,
    )
    effectiveness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    linked_policy_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<Control(id={self.id}, name='{self.name}', effectiveness={self.effectiveness})>"


class Regulation(Base):
    """A regulation or compliance framework relevant to an engagement."""

    __tablename__ = "regulations"
    __table_args__ = (Index("ix_regulations_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    framework: Mapped[str | None] = mapped_column(String(255), nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(255), nullable=True)
    obligations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<Regulation(id={self.id}, name='{self.name}', framework='{self.framework}')>"


class GapFinding(Base):
    """A detected governance gap where required controls are absent.

    Tracks CONTROL_GAP findings from automated gap detection against
    regulatory obligations. Historical findings are preserved; resolved
    gaps get a resolved_at timestamp.
    """

    __tablename__ = "gap_findings"
    __table_args__ = (
        Index("ix_gap_findings_engagement_id", "engagement_id"),
        Index("ix_gap_findings_activity_id", "activity_id"),
        Index("ix_gap_findings_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_elements.id", ondelete="CASCADE"), nullable=False
    )
    regulation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regulations.id", ondelete="SET NULL"), nullable=True
    )
    gap_type: Mapped[GovernanceGapType] = mapped_column(
        Enum(GovernanceGapType, values_callable=lambda e: [x.value for x in e]),
        default=GovernanceGapType.CONTROL_GAP,
        nullable=False,
    )
    severity: Mapped[GovernanceGapSeverity] = mapped_column(
        Enum(GovernanceGapSeverity, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    status: Mapped[GovernanceGapStatus] = mapped_column(
        Enum(GovernanceGapStatus, values_callable=lambda e: [x.value for x in e]),
        default=GovernanceGapStatus.OPEN,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    engagement: Mapped[Engagement] = relationship("Engagement")
    activity: Mapped[ProcessElement] = relationship("ProcessElement")
    regulation: Mapped[Regulation] = relationship("Regulation")

    def __repr__(self) -> str:
        return f"<GapFinding(id={self.id}, activity_id={self.activity_id}, type={self.gap_type}, status={self.status})>"


class ComplianceAssessment(Base):
    """A point-in-time compliance assessment for a process element.

    Tracks compliance state based on control coverage percentage.
    Historical records are maintained for trend analysis.
    """

    __tablename__ = "compliance_assessments"
    __table_args__ = (
        Index("ix_compliance_assessments_activity_id", "activity_id"),
        Index("ix_compliance_assessments_engagement_id", "engagement_id"),
        Index("ix_compliance_assessments_assessed_at", "assessed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_elements.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[ComplianceLevel] = mapped_column(
        Enum(ComplianceLevel, values_callable=lambda e: [x.value for x in e]),
        default=ComplianceLevel.NOT_ASSESSED,
        nullable=False,
    )
    control_coverage_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    total_required_controls: Mapped[int] = mapped_column(default=0, nullable=False)
    controls_with_evidence: Mapped[int] = mapped_column(default=0, nullable=False)
    gaps: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    assessed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    activity: Mapped[ProcessElement] = relationship("ProcessElement")
    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return f"<ComplianceAssessment(id={self.id}, activity_id={self.activity_id}, state={self.state})>"


class ControlEffectivenessScore(Base):
    """A point-in-time effectiveness score for a control.

    Scores are computed from evidence of control execution. Historical scores
    are preserved — each scoring run creates a new record.

    Effectiveness thresholds:
      >= 90% execution rate → HIGHLY_EFFECTIVE
      70-89% → EFFECTIVE
      50-69% → MODERATELY_EFFECTIVE
      < 50% → INEFFECTIVE
    """

    __tablename__ = "control_effectiveness_scores"
    __table_args__ = (
        Index("ix_control_effectiveness_scores_control_id", "control_id"),
        Index("ix_control_effectiveness_scores_engagement_id", "engagement_id"),
        Index("ix_control_effectiveness_scores_scored_at", "scored_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    control_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("controls.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    effectiveness: Mapped[ControlEffectiveness] = mapped_column(
        Enum(ControlEffectiveness, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    execution_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    evidence_source_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    scored_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    control: Mapped[Control] = relationship("Control")
    engagement: Mapped[Engagement] = relationship("Engagement")

    def __repr__(self) -> str:
        return (
            f"<ControlEffectivenessScore(id={self.id}, control_id={self.control_id}, "
            f"effectiveness={self.effectiveness})>"
        )
