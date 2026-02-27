"""Tests for the backward-compatible contradiction persistence bridge.

Tests DetectedContradiction and flatten_to_detected_contradictions which
map the three-way resolution result types to the Contradiction ORM schema.
"""

from __future__ import annotations

from src.pov.contradiction import (
    ContradictionResolutionResult,
    DetectedContradiction,
    GenuineDisagreement,
    NamingResolution,
    TemporalResolution,
    flatten_to_detected_contradictions,
    resolve_contradictions,
)


class TestDetectedContradiction:
    """Tests for the DetectedContradiction dataclass."""

    def test_default_fields(self):
        dc = DetectedContradiction()
        assert dc.element_name == ""
        assert dc.field_name == ""
        assert dc.values == []
        assert dc.resolution_value == ""
        assert dc.resolution_reason == ""
        assert dc.evidence_ids == []

    def test_custom_fields(self):
        dc = DetectedContradiction(
            element_name="Process Invoice",
            field_name="sequence_mismatch",
            values=[{"preferred": "A", "alternative": "B"}],
            resolution_value="A",
            resolution_reason="Higher weight source",
            evidence_ids=["ev1", "ev2"],
        )
        assert dc.element_name == "Process Invoice"
        assert dc.field_name == "sequence_mismatch"
        assert len(dc.evidence_ids) == 2


class TestFlattenToDetectedContradictions:
    """Tests for the flatten_to_detected_contradictions bridge function."""

    def test_empty_result(self):
        result = ContradictionResolutionResult()
        records = flatten_to_detected_contradictions(result)
        assert records == []

    def test_naming_resolution_flattened(self):
        result = ContradictionResolutionResult(
            naming_resolutions=[
                NamingResolution(
                    entity_name_a="Risk Assesment",
                    entity_name_b="Risk Assessment",
                    canonical_term="Risk Assessment",
                    merged_evidence_ids=["ev1", "ev2"],
                ),
            ],
        )
        records = flatten_to_detected_contradictions(result)

        assert len(records) == 1
        r = records[0]
        assert r.element_name == "Risk Assessment"
        assert r.field_name == "naming_variant"
        assert r.resolution_value == "Risk Assessment"
        assert "naming variant" in r.resolution_reason
        assert r.evidence_ids == ["ev1", "ev2"]

    def test_temporal_resolution_flattened(self):
        result = ContradictionResolutionResult(
            temporal_resolutions=[
                TemporalResolution(
                    element_name="Approve Loan",
                    older_value="2-step approval",
                    newer_value="1-step approval",
                    older_valid_to=2023,
                    newer_valid_from=2024,
                    older_evidence_ids=["ev1"],
                    newer_evidence_ids=["ev2"],
                ),
            ],
        )
        records = flatten_to_detected_contradictions(result)

        assert len(records) == 1
        r = records[0]
        assert r.element_name == "Approve Loan"
        assert r.field_name == "temporal_shift"
        assert r.resolution_value == "1-step approval"
        assert "2023" in r.resolution_reason
        assert "2024" in r.resolution_reason
        assert r.evidence_ids == ["ev1", "ev2"]

    def test_genuine_disagreement_flattened(self):
        result = ContradictionResolutionResult(
            genuine_disagreements=[
                GenuineDisagreement(
                    element_name="Review Contract",
                    mismatch_type="sequence_mismatch",
                    severity=0.8,
                    preferred_value="Before Approval",
                    alternative_value="After Approval",
                    preferred_evidence_ids=["ev1"],
                    alternative_evidence_ids=["ev2"],
                    resolution_reason="Weight differential: 0.30",
                ),
            ],
        )
        records = flatten_to_detected_contradictions(result)

        assert len(records) == 1
        r = records[0]
        assert r.element_name == "Review Contract"
        assert r.field_name == "sequence_mismatch"
        assert r.resolution_value == "Before Approval"
        assert "Weight differential" in r.resolution_reason
        assert r.evidence_ids == ["ev1", "ev2"]

    def test_mixed_results_flattened(self):
        """All three resolution types flatten correctly in one result."""
        result = ContradictionResolutionResult(
            naming_resolutions=[
                NamingResolution(
                    entity_name_a="Verify ID",
                    entity_name_b="Verify Id",
                    canonical_term="Verify ID",
                    merged_evidence_ids=["ev1", "ev2"],
                ),
            ],
            temporal_resolutions=[
                TemporalResolution(
                    element_name="KYC Review",
                    older_value="v1",
                    newer_value="v2",
                    older_valid_to=2022,
                    newer_valid_from=2023,
                    older_evidence_ids=["ev3"],
                    newer_evidence_ids=["ev4"],
                ),
            ],
            genuine_disagreements=[
                GenuineDisagreement(
                    element_name="Process Invoice",
                    mismatch_type="role_mismatch",
                    severity=0.5,
                    preferred_value="Analyst",
                    alternative_value="Manager",
                    preferred_evidence_ids=["ev5"],
                    alternative_evidence_ids=["ev6"],
                    resolution_reason="Role conflict",
                ),
            ],
        )
        records = flatten_to_detected_contradictions(result)

        assert len(records) == 3
        field_names = [r.field_name for r in records]
        assert "naming_variant" in field_names
        assert "temporal_shift" in field_names
        assert "role_mismatch" in field_names


class TestResolveContradictionsEmptyInput:
    """Test resolve_contradictions with empty inputs (smoke test)."""

    def test_empty_stubs_returns_empty_result(self):
        result = resolve_contradictions([], [])
        assert result.total_resolved == 0
        assert result.total_unresolved == 0
        assert result.naming_resolutions == []
        assert result.temporal_resolutions == []
        assert result.genuine_disagreements == []

    def test_no_seed_terms_defaults_to_empty(self):
        result = resolve_contradictions([], [], seed_terms=None)
        assert result.total_resolved == 0

    def test_single_stub_with_no_evidence_classifies_as_disagreement(self):
        """A conflict stub with nonexistent evidence falls through to genuine disagreement."""
        from src.pov.consensus import ConflictStub

        stub = ConflictStub(
            element_name="Test Element",
            preferred_value="A",
            alternative_value="B",
            preferred_evidence_ids=["nonexistent_1"],
            alternative_evidence_ids=["nonexistent_2"],
            disagreement_type="existence_mismatch",
        )
        result = resolve_contradictions([stub], [])
        assert result.total_unresolved == 1
        assert result.genuine_disagreements[0].element_name == "Test Element"
