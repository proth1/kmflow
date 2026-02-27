"""Tests for three-dimensional confidence model (Story #294).

Covers all 6 BDD scenarios from the acceptance criteria plus edge cases.
"""

from __future__ import annotations

import pytest

from src.api.schemas.confidence import ConfidenceScore
from src.semantic.confidence import (
    compute_confidence,
    compute_quality,
    compute_strength,
    derive_brightness,
    determine_evidence_grade,
    score_element,
)


class TestCompositeConfidenceScoreCalculation:
    """Scenario 1: Composite confidence score with Bright outcome."""

    def test_bright_outcome_full_formula(self):
        """Given high evidence factors, score is min(strength, quality) and BRIGHT."""
        coverage, agreement = 0.9, 0.8
        quality, reliability, recency = 0.7, 0.8, 0.9

        final, strength, quality_score = compute_confidence(coverage, agreement, quality, reliability, recency)

        expected_strength = (0.9 * 0.55) + (0.8 * 0.45)  # 0.855
        expected_quality = (0.7 * 0.40) + (0.8 * 0.35) + (0.9 * 0.25)  # 0.785
        expected_final = min(expected_strength, expected_quality)  # 0.785

        assert abs(strength - expected_strength) < 1e-9
        assert abs(quality_score - expected_quality) < 1e-9
        assert abs(final - expected_final) < 1e-9

    def test_bright_classification_and_mvc(self):
        """Score >= 0.75 with good grade → BRIGHT, MVC passed."""
        result = score_element(
            coverage=0.9,
            agreement=0.8,
            quality=0.7,
            reliability=0.8,
            recency=0.9,
            evidence_count=5,
            source_plane_count=3,
            has_sme_validation=True,
        )

        assert result.confidence_score == pytest.approx(0.785, abs=1e-3)
        assert result.brightness_classification == "bright"
        assert result.mvc_threshold_passed is True
        assert result.evidence_grade == "A"


class TestDarkBrightnessAndMVCFailure:
    """Scenario 2: Dark brightness and MVC failure."""

    def test_dark_classification(self):
        """Score < 0.40 → DARK, MVC fails."""
        cs = ConfidenceScore(
            confidence_score=0.35,
            strength_score=0.35,
            quality_score=0.40,
            evidence_grade="C",
        )
        assert cs.brightness_classification == "dark"
        assert cs.mvc_threshold_passed is False

    def test_low_factors_produce_dark(self):
        """Low input factors → dark brightness, MVC fails."""
        result = score_element(
            coverage=0.2,
            agreement=0.3,
            quality=0.2,
            reliability=0.3,
            recency=0.2,
            evidence_count=2,
            source_plane_count=1,
            has_sme_validation=False,
        )
        assert result.brightness_classification == "dark"
        assert result.mvc_threshold_passed is False


class TestEvidenceGradeA:
    """Scenario 3: Evidence Grade A assignment."""

    def test_grade_a_with_sme_and_multi_plane(self):
        """SME-validated + 2+ evidence planes → Grade A."""
        grade = determine_evidence_grade(
            evidence_count=4,
            source_plane_count=3,
            has_sme_validation=True,
        )
        assert grade == "A"

    def test_grade_a_brightness(self):
        """Grade A → brightness_from_grade is BRIGHT (no cap)."""
        brightness = derive_brightness(score=0.80, grade="A")
        assert brightness == "bright"


class TestEvidenceGradeDCoherenceConstraint:
    """Scenario 4: Evidence Grade D caps brightness at DIM."""

    def test_grade_d_single_source_unvalidated(self):
        """Single unvalidated source → Grade D."""
        grade = determine_evidence_grade(
            evidence_count=1,
            source_plane_count=1,
            has_sme_validation=False,
        )
        assert grade == "D"

    def test_grade_d_caps_brightness(self):
        """Grade D caps brightness at DIM even with high score."""
        brightness = derive_brightness(score=0.90, grade="D")
        assert brightness == "dim"

    def test_grade_d_full_element(self):
        """Full element scoring with Grade D shows DIM cap."""
        result = score_element(
            coverage=0.9,
            agreement=0.9,
            quality=0.9,
            reliability=0.9,
            recency=0.9,
            evidence_count=1,
            source_plane_count=1,
            has_sme_validation=False,
        )
        assert result.evidence_grade == "D"
        assert result.brightness_classification == "dim"


class TestEvidenceGradeUDarkRoom:
    """Scenario 5: Grade U for no evidence."""

    def test_grade_u_no_evidence(self):
        """No evidence → Grade U."""
        grade = determine_evidence_grade(
            evidence_count=0,
            source_plane_count=0,
            has_sme_validation=False,
        )
        assert grade == "U"

    def test_grade_u_brightness_dark(self):
        """Grade U with low score → DARK."""
        brightness = derive_brightness(score=0.0, grade="U")
        assert brightness == "dark"

    def test_grade_u_mvc_fails(self):
        """Grade U → MVC always fails (score must be 0 with no evidence)."""
        cs = ConfidenceScore(
            confidence_score=0.0,
            strength_score=0.0,
            quality_score=0.0,
            evidence_grade="U",
        )
        assert cs.mvc_threshold_passed is False


class TestBrightnessCoherenceConstraint:
    """Scenario 6: Brightness coherence constraint enforcement."""

    def test_high_score_grade_d_capped_at_dim(self):
        """Score=0.80 (would be BRIGHT) but Grade D → DIM."""
        cs = ConfidenceScore(
            confidence_score=0.80,
            strength_score=0.85,
            quality_score=0.80,
            evidence_grade="D",
        )
        assert cs.brightness_classification == "dim"

    def test_high_score_grade_u_capped_at_dim(self):
        """Grade U also caps at DIM."""
        cs = ConfidenceScore(
            confidence_score=0.80,
            strength_score=0.80,
            quality_score=0.80,
            evidence_grade="U",
        )
        assert cs.brightness_classification == "dim"

    def test_grade_c_no_cap(self):
        """Grade C does NOT cap brightness — BRIGHT if score allows."""
        cs = ConfidenceScore(
            confidence_score=0.80,
            strength_score=0.85,
            quality_score=0.80,
            evidence_grade="C",
        )
        assert cs.brightness_classification == "bright"


class TestComputeStrength:
    """Unit tests for strength sub-score."""

    def test_full_strength(self):
        assert compute_strength(1.0, 1.0) == pytest.approx(1.0)

    def test_zero_strength(self):
        assert compute_strength(0.0, 0.0) == pytest.approx(0.0)

    def test_weighted_correctly(self):
        result = compute_strength(0.5, 0.5)
        assert result == pytest.approx(0.5)


class TestComputeQuality:
    """Unit tests for quality sub-score."""

    def test_full_quality(self):
        assert compute_quality(1.0, 1.0, 1.0) == pytest.approx(1.0)

    def test_zero_quality(self):
        assert compute_quality(0.0, 0.0, 0.0) == pytest.approx(0.0)

    def test_weighted_correctly(self):
        result = compute_quality(0.5, 0.5, 0.5)
        assert result == pytest.approx(0.5)


class TestComputeConfidence:
    """Unit tests for the two-stage formula."""

    def test_min_of_strength_and_quality(self):
        """Final score is min(strength, quality)."""
        final, strength, quality_score = compute_confidence(
            coverage=1.0,
            agreement=1.0,
            quality=0.5,
            reliability=0.5,
            recency=0.5,
        )
        assert strength == pytest.approx(1.0)
        assert quality_score == pytest.approx(0.5)
        assert final == pytest.approx(0.5)

    def test_clamped_to_bounds(self):
        """Score never exceeds [0, 1]."""
        final, _, _ = compute_confidence(1.0, 1.0, 1.0, 1.0, 1.0)
        assert 0.0 <= final <= 1.0

        final, _, _ = compute_confidence(0.0, 0.0, 0.0, 0.0, 0.0)
        assert final == 0.0


class TestDetermineEvidenceGrade:
    """Unit tests for evidence grade determination."""

    def test_grade_b_multi_source_partial_validation(self):
        """2+ sources, validated but single plane → B."""
        grade = determine_evidence_grade(
            evidence_count=3,
            source_plane_count=1,
            has_sme_validation=True,
        )
        assert grade == "B"

    def test_grade_c_multi_source_no_validation(self):
        """2+ sources, no validation → C."""
        grade = determine_evidence_grade(
            evidence_count=3,
            source_plane_count=2,
            has_sme_validation=False,
        )
        assert grade == "C"


class TestDeriveBrightness:
    """Unit tests for brightness derivation."""

    def test_bright_with_good_grade(self):
        assert derive_brightness(0.80, "A") == "bright"

    def test_dim_by_score(self):
        assert derive_brightness(0.50, "A") == "dim"

    def test_dark_by_score(self):
        assert derive_brightness(0.20, "A") == "dark"

    def test_dim_cap_with_grade_d(self):
        assert derive_brightness(0.90, "D") == "dim"

    def test_dark_overrides_dim_cap(self):
        """Score-based DARK overrides grade-based DIM cap (dark < dim)."""
        assert derive_brightness(0.10, "D") == "dark"


class TestMVCThreshold:
    """Tests for Minimum Viable Confidence threshold."""

    def test_exactly_at_threshold(self):
        cs = ConfidenceScore(
            confidence_score=0.40,
            strength_score=0.40,
            quality_score=0.40,
            evidence_grade="C",
        )
        assert cs.mvc_threshold_passed is True

    def test_just_below_threshold(self):
        cs = ConfidenceScore(
            confidence_score=0.399,
            strength_score=0.399,
            quality_score=0.40,
            evidence_grade="C",
        )
        assert cs.mvc_threshold_passed is False
