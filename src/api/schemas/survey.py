"""Pydantic schemas for survey claims and epistemic frames."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.core.models.survey import (
    AUTHORITY_SCOPE_VOCABULARY,
    CertaintyTier,
    FrameKind,
    ProbeType,
)


class EpistemicFrameCreate(BaseModel):
    """Schema for creating an epistemic frame."""

    frame_kind: FrameKind
    authority_scope: str = Field(..., min_length=1, max_length=255)
    access_policy: str | None = None

    @field_validator("authority_scope")
    @classmethod
    def validate_authority_scope(cls, v: str) -> str:
        if v not in AUTHORITY_SCOPE_VOCABULARY:
            raise ValueError("authority_scope must be from the controlled engagement role vocabulary")
        return v


class EpistemicFrameRead(BaseModel):
    """Schema for reading an epistemic frame."""

    id: str
    claim_id: str
    frame_kind: str
    authority_scope: str
    access_policy: str | None = None
    created_at: str


class SurveyClaimCreate(BaseModel):
    """Schema for creating a survey claim."""

    engagement_id: UUID
    session_id: UUID
    probe_type: ProbeType
    respondent_role: str = Field(..., min_length=1, max_length=255)
    claim_text: str = Field(..., min_length=1)
    certainty_tier: CertaintyTier
    proof_expectation: str | None = None
    related_seed_terms: list[str] | None = None
    epistemic_frame: EpistemicFrameCreate | None = None


class SurveyClaimRead(BaseModel):
    """Schema for reading a survey claim."""

    id: str
    engagement_id: str
    session_id: str
    probe_type: str
    respondent_role: str
    claim_text: str
    certainty_tier: str
    proof_expectation: str | None = None
    related_seed_terms: list[str] | None = None
    epistemic_frame: EpistemicFrameRead | None = None
    created_at: str
