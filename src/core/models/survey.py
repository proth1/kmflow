"""Survey claim and epistemic frame models for structured knowledge elicitation."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class CertaintyTier(enum.StrEnum):
    """Certainty levels for survey claims."""

    KNOWN = "known"
    SUSPECTED = "suspected"
    UNKNOWN = "unknown"
    CONTRADICTED = "contradicted"


class ProbeType(enum.StrEnum):
    """Probe types mapping to the 9 universal process knowledge forms.

    From PRD Section 6.10.2 structured survey bot.
    """

    EXISTENCE = "existence"
    SEQUENCE = "sequence"
    DEPENDENCY = "dependency"
    INPUT_OUTPUT = "input_output"
    GOVERNANCE = "governance"
    PERFORMER = "performer"
    EXCEPTION = "exception"
    UNCERTAINTY = "uncertainty"


class FrameKind(enum.StrEnum):
    """Epistemic frame kinds for knowledge assertions."""

    PROCEDURAL = "procedural"
    REGULATORY = "regulatory"
    EXPERIENTIAL = "experiential"
    TELEMETRIC = "telemetric"
    ELICITED = "elicited"
    BEHAVIORAL = "behavioral"


# Controlled vocabulary for authority_scope.
# These are engagement roles that can assert knowledge, not freeform strings.
AUTHORITY_SCOPE_VOCABULARY: frozenset[str] = frozenset(
    {
        "operations_team",
        "compliance_officer",
        "process_owner",
        "system_administrator",
        "business_analyst",
        "risk_manager",
        "quality_assurance",
        "external_auditor",
        "system_telemetry",
        "task_mining_agent",
        "survey_respondent",
        "subject_matter_expert",
    }
)


class SurveyClaim(Base):
    """A knowledge claim from a structured survey or interview session."""

    __tablename__ = "survey_claims"
    __table_args__ = (
        Index("ix_survey_claims_engagement_id", "engagement_id"),
        Index("ix_survey_claims_session_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    probe_type: Mapped[ProbeType] = mapped_column(
        Enum(ProbeType, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    respondent_role: Mapped[str] = mapped_column(String(255), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    certainty_tier: Mapped[CertaintyTier] = mapped_column(
        Enum(CertaintyTier, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    proof_expectation: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_seed_terms: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    epistemic_frame: Mapped[EpistemicFrame | None] = relationship(
        "EpistemicFrame", back_populates="survey_claim", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SurveyClaim(id={self.id}, certainty={self.certainty_tier}, probe={self.probe_type})>"


class EpistemicFrame(Base):
    """Epistemic context for a survey claim or knowledge assertion."""

    __tablename__ = "epistemic_frames"
    __table_args__ = (
        Index("ix_epistemic_frames_claim_id", "claim_id"),
        Index("ix_epistemic_frames_engagement_id", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("survey_claims.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # Direct engagement_id per PRD Section 6.2 — enables independent engagement
    # scoping for frames beyond survey claims (e.g., on semantic relationships).
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    frame_kind: Mapped[FrameKind] = mapped_column(
        Enum(FrameKind, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    authority_scope: Mapped[str] = mapped_column(String(255), nullable=False)
    access_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    survey_claim: Mapped[SurveyClaim] = relationship("SurveyClaim", back_populates="epistemic_frame")

    def __repr__(self) -> str:
        return f"<EpistemicFrame(id={self.id}, kind={self.frame_kind}, scope={self.authority_scope})>"
