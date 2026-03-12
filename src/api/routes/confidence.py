"""Confidence scoring API routes (KMFLOW-67).

Exposes the three-dimensional confidence scoring service for computing
strength, quality, and final confidence scores with brightness classification.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.core.auth import get_current_user
from src.core.models import User

router = APIRouter(prefix="/api/v1/confidence", tags=["confidence"])


# -- Request/Response Schemas ------------------------------------------------


class ConfidenceRequest(BaseModel):
    """Request to compute a confidence score."""

    coverage: float = Field(..., ge=0.0, le=1.0, description="Evidence coverage (0-1)")
    agreement: float = Field(..., ge=0.0, le=1.0, description="Evidence agreement (0-1)")
    quality: float = Field(..., ge=0.0, le=1.0, description="Evidence quality (0-1)")
    reliability: float = Field(..., ge=0.0, le=1.0, description="Source reliability (0-1)")
    recency: float = Field(..., ge=0.0, le=1.0, description="Evidence recency (0-1)")
    evidence_count: int = Field(0, ge=0, description="Number of evidence items")
    source_plane_count: int = Field(0, ge=0, description="Number of distinct evidence planes")
    has_sme_validation: bool = Field(False, description="Whether SME has validated")


class ConfidenceResponse(BaseModel):
    """Response with computed confidence scores."""

    final_score: float
    strength: float
    quality_score: float
    evidence_grade: str
    brightness: str


class BatchConfidenceRequest(BaseModel):
    """Request to compute confidence scores for multiple items."""

    items: list[ConfidenceRequest] = Field(..., min_length=1, max_length=500)


class BatchConfidenceResponse(BaseModel):
    """Response with batch confidence scores."""

    results: list[ConfidenceResponse]
    count: int


# -- Endpoints ---------------------------------------------------------------


@router.post("/compute", response_model=ConfidenceResponse)
async def compute_confidence_endpoint(
    body: ConfidenceRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Compute a three-dimensional confidence score.

    Implements the PRD v2.1 two-stage formula:
    - Stage 1a: strength = coverage * 0.55 + agreement * 0.45
    - Stage 1b: quality = quality * 0.40 + reliability * 0.35 + recency * 0.25
    - Stage 2: final = min(strength, quality)

    Also derives evidence grade (A-U) and brightness (bright/dim/dark).
    """
    from src.semantic.confidence import (
        compute_confidence,
        derive_brightness,
        determine_evidence_grade,
    )

    final_score, strength, quality_score = compute_confidence(
        coverage=body.coverage,
        agreement=body.agreement,
        quality=body.quality,
        reliability=body.reliability,
        recency=body.recency,
    )

    grade = determine_evidence_grade(
        evidence_count=body.evidence_count,
        source_plane_count=body.source_plane_count,
        has_sme_validation=body.has_sme_validation,
    )

    brightness = derive_brightness(final_score, grade)

    return {
        "final_score": round(final_score, 4),
        "strength": round(strength, 4),
        "quality_score": round(quality_score, 4),
        "evidence_grade": grade,
        "brightness": brightness,
    }


@router.post("/compute/batch", response_model=BatchConfidenceResponse)
async def compute_confidence_batch_endpoint(
    body: BatchConfidenceRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Compute confidence scores for multiple items in a single request."""
    from src.semantic.confidence import (
        compute_confidence,
        derive_brightness,
        determine_evidence_grade,
    )

    results = []
    for item in body.items:
        final_score, strength, quality_score = compute_confidence(
            coverage=item.coverage,
            agreement=item.agreement,
            quality=item.quality,
            reliability=item.reliability,
            recency=item.recency,
        )

        grade = determine_evidence_grade(
            evidence_count=item.evidence_count,
            source_plane_count=item.source_plane_count,
            has_sme_validation=item.has_sme_validation,
        )

        brightness = derive_brightness(final_score, grade)

        results.append(
            {
                "final_score": round(final_score, 4),
                "strength": round(strength, 4),
                "quality_score": round(quality_score, 4),
                "evidence_grade": grade,
                "brightness": brightness,
            }
        )

    return {
        "results": results,
        "count": len(results),
    }
