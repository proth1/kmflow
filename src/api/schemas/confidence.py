"""Pydantic schemas for the three-dimensional confidence model."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from src.pov.constants import (
    BRIGHTNESS_BRIGHT_THRESHOLD,
    BRIGHTNESS_DIM_THRESHOLD,
    GRADES_CAPPED_AT_DIM,
    MVC_THRESHOLD,
)


class ConfidenceInput(BaseModel):
    """Raw input factors for confidence calculation."""

    evidence_coverage: float = Field(..., ge=0.0, le=1.0)
    evidence_agreement: float = Field(..., ge=0.0, le=1.0)
    evidence_quality: float = Field(..., ge=0.0, le=1.0)
    source_reliability: float = Field(..., ge=0.0, le=1.0)
    evidence_recency: float = Field(..., ge=0.0, le=1.0)


class ConfidenceScore(BaseModel):
    """Three-dimensional confidence model result.

    Dimensions:
        1. confidence_score (0-1): min(strength, quality)
        2. evidence_grade (A/B/C/D/U): qualitative grade from evidence assessment
        3. brightness_classification (BRIGHT/DIM/DARK): derived with coherence constraint
    """

    confidence_score: float = Field(..., ge=0.0, le=1.0)
    strength_score: float = Field(..., ge=0.0, le=1.0)
    quality_score: float = Field(..., ge=0.0, le=1.0)
    evidence_grade: str = Field(..., pattern=r"^[ABCDU]$")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def brightness_classification(self) -> str:
        """Derive brightness with coherence constraint.

        Score-based brightness:
            BRIGHT >= 0.75, DIM >= 0.40, DARK < 0.40

        Coherence constraint:
            Grade D or U caps brightness at DIM regardless of score.
        """
        # Score-based brightness
        if self.confidence_score >= BRIGHTNESS_BRIGHT_THRESHOLD:
            score_brightness = "bright"
        elif self.confidence_score >= BRIGHTNESS_DIM_THRESHOLD:
            score_brightness = "dim"
        else:
            score_brightness = "dark"

        # Grade-based brightness
        grade_brightness = "dim" if self.evidence_grade in GRADES_CAPPED_AT_DIM else "bright"

        # Final = min(score_brightness, grade_brightness)
        # Order: dark < dim < bright
        order = {"dark": 0, "dim": 1, "bright": 2}
        final = min(score_brightness, grade_brightness, key=lambda b: order[b])
        return final

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mvc_threshold_passed(self) -> bool:
        """Whether the element meets Minimum Viable Confidence."""
        return self.confidence_score >= MVC_THRESHOLD


class ConfidenceResponse(BaseModel):
    """API response wrapper for confidence scoring."""

    element_id: str
    confidence_score: float
    strength_score: float
    quality_score: float
    evidence_grade: str
    brightness_classification: str
    mvc_threshold_passed: bool
