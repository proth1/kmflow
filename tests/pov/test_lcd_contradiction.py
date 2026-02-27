"""BDD tests for LCD contradiction resolution (Story #312).

Tests the three-way distinction classifier (naming variant, temporal shift,
genuine disagreement), severity scoring, ConflictObject creation, and
epistemic frame annotation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

from src.core.models.conflict import MismatchType, ResolutionType
from src.pov.consensus import ConflictStub
from src.pov.contradiction import (
    _edit_distance,
    classify_conflict,
    compute_severity,
    detect_naming_variant,
    detect_temporal_shift,
    resolve_contradictions,
)

# -- Test helpers ------------------------------------------------------------


def _make_evidence(
    evidence_id: str | None = None,
    category: str = "documents",
    quality_score: float = 0.8,
    freshness_score: float = 0.7,
    source_date: datetime | None = None,
) -> MagicMock:
    """Create a mock EvidenceItem for testing."""
    item = MagicMock()
    item.id = evidence_id or str(uuid.uuid4())
    item.category = category
    item.quality_score = quality_score
    item.freshness_score = freshness_score
    item.source_date = source_date
    return item


def _make_stub(
    element_name: str = "Test Element",
    disagreement_type: str = "sequence_mismatch",
    preferred_value: str = "Activity A",
    alternative_value: str = "Activity B",
    preferred_evidence_ids: list[str] | None = None,
    alternative_evidence_ids: list[str] | None = None,
    resolution_reason: str = "Higher source weight",
) -> ConflictStub:
    """Create a ConflictStub for testing."""
    return ConflictStub(
        element_name=element_name,
        disagreement_type=disagreement_type,
        preferred_value=preferred_value,
        alternative_value=alternative_value,
        preferred_evidence_ids=preferred_evidence_ids or ["ev-1"],
        alternative_evidence_ids=alternative_evidence_ids or ["ev-2"],
        resolution_reason=resolution_reason,
    )


# -- Scenario 1: Sequence conflict produces ConflictObject with severity ------


class TestSequenceConflictProducesConflictObject:
    """BDD Scenario: Sequence conflict produces ConflictObject with severity."""

    def test_sequence_conflict_creates_genuine_disagreement(self) -> None:
        """Given conflicting sequences from system data and job aid,
        when resolver processes, then a genuine disagreement is created."""
        ev_a = _make_evidence("ev-sys", category="structured_data", source_date=datetime(2025, 1, 1, tzinfo=UTC))
        ev_b = _make_evidence("ev-job", category="job_aids_edge_cases", source_date=datetime(2025, 1, 1, tzinfo=UTC))

        stub = _make_stub(
            element_name="Process Step X",
            disagreement_type=MismatchType.SEQUENCE_MISMATCH.value,
            preferred_value="Activity_A -> Activity_B",
            alternative_value="Activity_B -> Activity_A",
            preferred_evidence_ids=["ev-sys"],
            alternative_evidence_ids=["ev-job"],
        )

        result = resolve_contradictions([stub], [ev_a, ev_b])

        assert len(result.genuine_disagreements) == 1
        gd = result.genuine_disagreements[0]
        assert gd.mismatch_type == "sequence_mismatch"

    def test_severity_computed_from_weight_differential(self) -> None:
        """Severity reflects the weight differential between sources."""
        ev_a = _make_evidence("ev-sys", category="structured_data")
        ev_b = _make_evidence("ev-job", category="job_aids_edge_cases")

        stub = _make_stub(
            disagreement_type=MismatchType.SEQUENCE_MISMATCH.value,
            preferred_evidence_ids=["ev-sys"],
            alternative_evidence_ids=["ev-job"],
        )

        result = resolve_contradictions([stub], [ev_a, ev_b])
        gd = result.genuine_disagreements[0]

        # system_data weight=1.0, job_aids=0.3, diff=0.7
        # severity = 1.0 * 0.6 + 0.7 * 0.4 = 0.88
        assert gd.severity > 0.8

    def test_conflict_references_both_sources(self) -> None:
        """ConflictObject references both Source A and Source B evidence."""
        ev_a = _make_evidence("ev-sys", category="structured_data")
        ev_b = _make_evidence("ev-job", category="job_aids_edge_cases")

        stub = _make_stub(
            preferred_evidence_ids=["ev-sys"],
            alternative_evidence_ids=["ev-job"],
        )

        result = resolve_contradictions([stub], [ev_a, ev_b])
        gd = result.genuine_disagreements[0]

        assert "ev-sys" in gd.preferred_evidence_ids
        assert "ev-job" in gd.alternative_evidence_ids

    def test_preferred_sequence_from_higher_weight(self) -> None:
        """Preferred value is from the higher-weight source (system data)."""
        ev_a = _make_evidence("ev-sys", category="structured_data")
        ev_b = _make_evidence("ev-job", category="job_aids_edge_cases")

        stub = _make_stub(
            preferred_value="A -> B",
            alternative_value="B -> A",
            preferred_evidence_ids=["ev-sys"],
            alternative_evidence_ids=["ev-job"],
        )

        result = resolve_contradictions([stub], [ev_a, ev_b])
        gd = result.genuine_disagreements[0]

        assert gd.preferred_value == "A -> B"
        assert gd.alternative_value == "B -> A"


# -- Scenario 2: Naming variant resolved via seed list ------------------------


class TestNamingVariantResolvedViaSeedList:
    """BDD Scenario: Naming variant resolved via seed list."""

    def test_naming_variant_detected_with_seed_term(self) -> None:
        """Given two similar names and a matching seed term,
        when three-way analysis runs, then it's classified as naming variant."""
        # "Risk Assessment" (exact) and "Risk Assesment" (typo, edit dist 1)
        seed_terms = ["Risk Assessment"]
        canonical = detect_naming_variant("Risk Assessment", "Risk Assesment", seed_terms)
        assert canonical == "Risk Assessment"

    def test_both_entities_within_edit_distance_2(self) -> None:
        """Both raw terms are within edit distance 2 of the canonical seed term."""
        seed = "Risk Assessment"
        dist1 = _edit_distance("Risk Assessment", seed)  # exact match
        dist2 = _edit_distance("Risk Assesment", seed)  # 1 deletion
        assert dist1 == 0
        assert dist2 <= 2

    def test_naming_variant_merges_evidence(self) -> None:
        """Both source evidence links are preserved on the merged entity."""
        ev_a = _make_evidence("ev-a", category="documents")
        ev_b = _make_evidence("ev-b", category="documents")

        stub = _make_stub(
            preferred_value="Risk Assessment",
            alternative_value="Risk Assesment",
            preferred_evidence_ids=["ev-a"],
            alternative_evidence_ids=["ev-b"],
        )

        result = resolve_contradictions([stub], [ev_a, ev_b], seed_terms=["Risk Assessment"])

        assert len(result.naming_resolutions) == 1
        nr = result.naming_resolutions[0]
        assert "ev-a" in nr.merged_evidence_ids
        assert "ev-b" in nr.merged_evidence_ids
        assert nr.canonical_term == "Risk Assessment"

    def test_naming_variant_creates_no_conflict_object(self) -> None:
        """No ConflictObject is created for naming variants."""
        ev_a = _make_evidence("ev-a", category="documents")
        ev_b = _make_evidence("ev-b", category="documents")

        stub = _make_stub(
            preferred_value="Approve Loan",
            alternative_value="Aprove Loan",  # typo, edit distance 1
            preferred_evidence_ids=["ev-a"],
            alternative_evidence_ids=["ev-b"],
        )

        result = resolve_contradictions([stub], [ev_a, ev_b], seed_terms=["Approve Loan"])

        assert len(result.genuine_disagreements) == 0
        assert result.total_resolved == 1

    def test_naming_variant_resolution_type(self) -> None:
        """Resolution type is set to NAMING_VARIANT."""
        ev_a = _make_evidence("ev-a")
        ev_b = _make_evidence("ev-b")

        stub = _make_stub(
            preferred_value="Risk Assessment",
            alternative_value="Risk Assesment",  # typo = edit distance 1
            preferred_evidence_ids=["ev-a"],
            alternative_evidence_ids=["ev-b"],
        )

        seed_terms = ["Risk Assessment"]
        evidence_map = {"ev-a": ev_a, "ev-b": ev_b}

        classification = classify_conflict(stub, evidence_map, seed_terms)
        assert classification == ResolutionType.NAMING_VARIANT.value


# -- Scenario 3: Temporal shift resolved via bitemporal validity --------------


class TestTemporalShiftResolvedViaBitemporalValidity:
    """BDD Scenario: Temporal shift resolved via bitemporal validity."""

    def test_temporal_shift_detected_from_date_gap(self) -> None:
        """Given two high-quality docs with 3-year gap, temporal shift detected."""
        ev_old = _make_evidence(
            "ev-old", category="documents",
            source_date=datetime(2022, 6, 15, tzinfo=UTC),
        )
        ev_new = _make_evidence(
            "ev-new", category="documents",
            source_date=datetime(2025, 3, 1, tzinfo=UTC),
        )

        assert detect_temporal_shift(ev_old, ev_new) is True

    def test_temporal_shift_not_detected_for_small_gap(self) -> None:
        """No temporal shift when sources are within 1 year."""
        ev_a = _make_evidence(
            "ev-a", category="documents",
            source_date=datetime(2024, 1, 1, tzinfo=UTC),
        )
        ev_b = _make_evidence(
            "ev-b", category="documents",
            source_date=datetime(2025, 1, 1, tzinfo=UTC),
        )

        assert detect_temporal_shift(ev_a, ev_b) is False

    def test_temporal_shift_only_for_document_categories(self) -> None:
        """Temporal shift requires document-class evidence on both sides."""
        ev_doc = _make_evidence(
            "ev-doc", category="documents",
            source_date=datetime(2020, 1, 1, tzinfo=UTC),
        )
        ev_sys = _make_evidence(
            "ev-sys", category="structured_data",
            source_date=datetime(2025, 1, 1, tzinfo=UTC),
        )

        assert detect_temporal_shift(ev_doc, ev_sys) is False

    def test_temporal_resolution_stamps_validity(self) -> None:
        """Bitemporal validity stamps: older gets valid_to, newer gets valid_from."""
        ev_old = _make_evidence(
            "ev-old", category="documents",
            source_date=datetime(2022, 6, 15, tzinfo=UTC),
        )
        ev_new = _make_evidence(
            "ev-new", category="documents",
            source_date=datetime(2025, 3, 1, tzinfo=UTC),
        )

        stub = _make_stub(
            element_name="Approval Rule",
            preferred_value="Automated Approval",
            alternative_value="Manual Approval",
            preferred_evidence_ids=["ev-new"],
            alternative_evidence_ids=["ev-old"],
        )

        result = resolve_contradictions([stub], [ev_old, ev_new])

        assert len(result.temporal_resolutions) == 1
        tr = result.temporal_resolutions[0]
        assert tr.older_valid_to == 2024  # newer year - 1
        assert tr.newer_valid_from == 2025

    def test_temporal_shift_creates_no_conflict_object(self) -> None:
        """Temporal shifts are resolvable — no ConflictObject created."""
        ev_old = _make_evidence(
            "ev-old", category="documents",
            source_date=datetime(2022, 1, 1, tzinfo=UTC),
        )
        ev_new = _make_evidence(
            "ev-new", category="bpm_process_models",
            source_date=datetime(2025, 1, 1, tzinfo=UTC),
        )

        stub = _make_stub(
            preferred_evidence_ids=["ev-new"],
            alternative_evidence_ids=["ev-old"],
        )

        result = resolve_contradictions([stub], [ev_old, ev_new])

        assert len(result.genuine_disagreements) == 0
        assert result.total_resolved == 1

    def test_temporal_resolution_preserves_evidence_ids(self) -> None:
        """Both source evidence links preserved on temporal resolution."""
        ev_old = _make_evidence(
            "ev-old", category="documents",
            source_date=datetime(2022, 1, 1, tzinfo=UTC),
        )
        ev_new = _make_evidence(
            "ev-new", category="documents",
            source_date=datetime(2025, 1, 1, tzinfo=UTC),
        )

        stub = _make_stub(
            preferred_evidence_ids=["ev-new"],
            alternative_evidence_ids=["ev-old"],
        )

        result = resolve_contradictions([stub], [ev_old, ev_new])
        tr = result.temporal_resolutions[0]

        all_ids = tr.older_evidence_ids + tr.newer_evidence_ids
        assert "ev-old" in all_ids
        assert "ev-new" in all_ids


# -- Scenario 4: Genuine disagreement preserved with epistemic frames ---------


class TestGenuineDisagreementWithEpistemicFrames:
    """BDD Scenario: Genuine disagreement preserved with epistemic frames."""

    def test_genuine_disagreement_creates_conflict_object(self) -> None:
        """When naming variant and temporal shift don't apply, genuine disagreement."""
        ev_interview = _make_evidence(
            "ev-sme", category="audio",
            source_date=datetime(2025, 1, 1, tzinfo=UTC),
        )
        ev_system = _make_evidence(
            "ev-sys", category="structured_data",
            source_date=datetime(2025, 1, 1, tzinfo=UTC),
        )

        stub = _make_stub(
            element_name="Secondary Review",
            disagreement_type=MismatchType.EXISTENCE_MISMATCH.value,
            preferred_value="Always occurs",
            alternative_value="Occurs 15% of cases",
            preferred_evidence_ids=["ev-sys"],
            alternative_evidence_ids=["ev-sme"],
        )

        result = resolve_contradictions([stub], [ev_interview, ev_system])

        assert len(result.genuine_disagreements) == 1
        gd = result.genuine_disagreements[0]
        assert gd.element_name == "Secondary Review"
        assert gd.mismatch_type == "existence_mismatch"

    def test_epistemic_frame_for_system_observation(self) -> None:
        """System evidence gets authority = system_telemetry, kind = telemetric."""
        ev_sys = _make_evidence("ev-sys", category="structured_data")
        ev_sme = _make_evidence("ev-sme", category="audio")

        stub = _make_stub(
            preferred_evidence_ids=["ev-sys"],
            alternative_evidence_ids=["ev-sme"],
        )

        result = resolve_contradictions([stub], [ev_sys, ev_sme])
        gd = result.genuine_disagreements[0]

        assert gd.preferred_authority == "system_telemetry"
        assert gd.preferred_frame_kind == "telemetric"

    def test_epistemic_frame_for_expert_claim(self) -> None:
        """SME interview evidence gets authority = subject_matter_expert."""
        ev_sys = _make_evidence("ev-sys", category="structured_data")
        ev_sme = _make_evidence("ev-sme", category="audio")

        stub = _make_stub(
            preferred_evidence_ids=["ev-sys"],
            alternative_evidence_ids=["ev-sme"],
        )

        result = resolve_contradictions([stub], [ev_sys, ev_sme])
        gd = result.genuine_disagreements[0]

        assert gd.alternative_authority == "subject_matter_expert"
        assert gd.alternative_frame_kind == "elicited"

    def test_genuine_disagreement_flagged_for_sme_validation(self) -> None:
        """Genuine disagreements are flagged for SME validation."""
        ev_sys = _make_evidence("ev-sys", category="structured_data")
        ev_sme = _make_evidence("ev-sme", category="audio")

        stub = _make_stub(
            preferred_evidence_ids=["ev-sys"],
            alternative_evidence_ids=["ev-sme"],
        )

        result = resolve_contradictions([stub], [ev_sys, ev_sme])
        gd = result.genuine_disagreements[0]

        assert gd.needs_sme_validation is True

    def test_both_views_preserved(self) -> None:
        """Both preferred and alternative values are preserved."""
        ev_sys = _make_evidence("ev-sys", category="structured_data")
        ev_sme = _make_evidence("ev-sme", category="audio")

        stub = _make_stub(
            preferred_value="System View",
            alternative_value="Expert View",
            preferred_evidence_ids=["ev-sys"],
            alternative_evidence_ids=["ev-sme"],
        )

        result = resolve_contradictions([stub], [ev_sys, ev_sme])
        gd = result.genuine_disagreements[0]

        assert gd.preferred_value == "System View"
        assert gd.alternative_value == "Expert View"


# -- Scenario 5: ConflictObject queryable with evidence ----------------------


class TestConflictObjectQueryable:
    """BDD Scenario: ConflictObject fully queryable with evidence for both views."""

    def test_genuine_disagreement_has_mismatch_type(self) -> None:
        """Response includes the conflict disagreement_type."""
        ev_a = _make_evidence("ev-a", category="structured_data")
        ev_b = _make_evidence("ev-b", category="job_aids_edge_cases")

        stub = _make_stub(
            disagreement_type=MismatchType.ROLE_MISMATCH.value,
            preferred_evidence_ids=["ev-a"],
            alternative_evidence_ids=["ev-b"],
        )

        result = resolve_contradictions([stub], [ev_a, ev_b])
        gd = result.genuine_disagreements[0]

        assert gd.mismatch_type == "role_mismatch"

    def test_genuine_disagreement_has_severity(self) -> None:
        """Response includes computed severity score."""
        ev_a = _make_evidence("ev-a", category="structured_data")
        ev_b = _make_evidence("ev-b", category="job_aids_edge_cases")

        stub = _make_stub(
            disagreement_type=MismatchType.ROLE_MISMATCH.value,
            preferred_evidence_ids=["ev-a"],
            alternative_evidence_ids=["ev-b"],
        )

        result = resolve_contradictions([stub], [ev_a, ev_b])
        gd = result.genuine_disagreements[0]

        assert 0.0 <= gd.severity <= 1.0

    def test_includes_supporting_evidence_for_both_views(self) -> None:
        """Both preferred and alternative views have their evidence IDs."""
        ev_a = _make_evidence("ev-a", category="documents")
        ev_b = _make_evidence("ev-b", category="audio")

        stub = _make_stub(
            preferred_evidence_ids=["ev-a"],
            alternative_evidence_ids=["ev-b"],
        )

        result = resolve_contradictions([stub], [ev_a, ev_b])
        gd = result.genuine_disagreements[0]

        assert len(gd.preferred_evidence_ids) > 0
        assert len(gd.alternative_evidence_ids) > 0

    def test_includes_resolution_reason(self) -> None:
        """Response includes resolution_reason explanation."""
        ev_a = _make_evidence("ev-a", category="structured_data")
        ev_b = _make_evidence("ev-b", category="audio")

        stub = _make_stub(
            preferred_evidence_ids=["ev-a"],
            alternative_evidence_ids=["ev-b"],
        )

        result = resolve_contradictions([stub], [ev_a, ev_b])
        gd = result.genuine_disagreements[0]

        assert "naming variance" in gd.resolution_reason.lower()
        assert "temporal shift" in gd.resolution_reason.lower()


# -- Severity scoring tests ---------------------------------------------------


class TestSeverityScoring:
    """Tests for the severity computation formula."""

    def test_sequence_mismatch_highest_criticality(self) -> None:
        """Sequence mismatch has criticality 1.0."""
        severity = compute_severity("sequence_mismatch", 1.0, 0.3)
        # 1.0 * 0.6 + 0.7 * 0.4 = 0.88
        assert severity > 0.85

    def test_control_gap_lowest_criticality(self) -> None:
        """Control gap has criticality 0.4."""
        severity = compute_severity("control_gap", 0.5, 0.5)
        # 0.4 * 0.6 + 0.0 * 0.4 = 0.24
        assert severity < 0.3

    def test_severity_clamped_to_01(self) -> None:
        """Severity stays in [0.0, 1.0] range."""
        s1 = compute_severity("sequence_mismatch", 1.0, 0.0)
        assert 0.0 <= s1 <= 1.0

        s2 = compute_severity("control_gap", 0.5, 0.5)
        assert 0.0 <= s2 <= 1.0

    def test_higher_weight_differential_increases_severity(self) -> None:
        """Larger weight differential produces higher severity."""
        low_diff = compute_severity("role_mismatch", 0.5, 0.4)
        high_diff = compute_severity("role_mismatch", 1.0, 0.3)
        assert high_diff > low_diff

    def test_criticality_order(self) -> None:
        """SEQUENCE > EXISTENCE > RULE > IO > ROLE > CONTROL_GAP."""
        weight_a, weight_b = 0.7, 0.3  # Same differential
        s_seq = compute_severity("sequence_mismatch", weight_a, weight_b)
        s_exist = compute_severity("existence_mismatch", weight_a, weight_b)
        s_rule = compute_severity("rule_mismatch", weight_a, weight_b)
        s_io = compute_severity("io_mismatch", weight_a, weight_b)
        s_role = compute_severity("role_mismatch", weight_a, weight_b)
        s_ctrl = compute_severity("control_gap", weight_a, weight_b)

        assert s_seq > s_exist > s_rule > s_io > s_role > s_ctrl


# -- Edit distance tests ------------------------------------------------------


class TestEditDistance:
    """Tests for Levenshtein edit distance."""

    def test_identical_strings(self) -> None:
        """Identical strings have distance 0."""
        assert _edit_distance("hello", "hello") == 0

    def test_case_insensitive(self) -> None:
        """Distance is case-insensitive."""
        assert _edit_distance("Hello", "hello") == 0

    def test_single_substitution(self) -> None:
        """One character difference = distance 1."""
        assert _edit_distance("cat", "bat") == 1

    def test_insertion(self) -> None:
        """One insertion = distance 1."""
        assert _edit_distance("cat", "cart") == 1

    def test_deletion(self) -> None:
        """One deletion = distance 1."""
        assert _edit_distance("cart", "cat") == 1

    def test_empty_string(self) -> None:
        """Distance to empty string is length of other."""
        assert _edit_distance("hello", "") == 5
        assert _edit_distance("", "world") == 5


# -- Three-way classification tests -------------------------------------------


class TestThreeWayClassification:
    """Tests for the three-way distinction classifier."""

    def test_classifies_naming_variant_first(self) -> None:
        """Naming variant check takes priority over temporal shift."""
        ev_a = _make_evidence("ev-a", category="documents", source_date=datetime(2020, 1, 1, tzinfo=UTC))
        ev_b = _make_evidence("ev-b", category="documents", source_date=datetime(2025, 1, 1, tzinfo=UTC))
        evidence_map = {"ev-a": ev_a, "ev-b": ev_b}

        stub = _make_stub(
            preferred_value="Verify Identity",
            alternative_value="Verify Identiy",  # typo, edit distance 1
            preferred_evidence_ids=["ev-a"],
            alternative_evidence_ids=["ev-b"],
        )

        # Even though dates are 5 years apart, naming variant wins
        classification = classify_conflict(stub, evidence_map, seed_terms=["Verify Identity"])
        assert classification == "naming_variant"

    def test_classifies_temporal_shift_when_no_seed_match(self) -> None:
        """When no naming variant match, temporal shift check applies."""
        ev_old = _make_evidence("ev-old", category="documents", source_date=datetime(2020, 1, 1, tzinfo=UTC))
        ev_new = _make_evidence("ev-new", category="documents", source_date=datetime(2025, 1, 1, tzinfo=UTC))
        evidence_map = {"ev-old": ev_old, "ev-new": ev_new}

        stub = _make_stub(
            preferred_value="Manual Process",
            alternative_value="Automated Process",
            preferred_evidence_ids=["ev-old"],
            alternative_evidence_ids=["ev-new"],
        )

        classification = classify_conflict(stub, evidence_map, seed_terms=[])
        assert classification == "temporal_shift"

    def test_falls_back_to_genuine_disagreement(self) -> None:
        """When neither naming variant nor temporal shift, genuine disagreement."""
        ev_a = _make_evidence("ev-a", category="structured_data", source_date=datetime(2025, 1, 1, tzinfo=UTC))
        ev_b = _make_evidence("ev-b", category="audio", source_date=datetime(2025, 1, 1, tzinfo=UTC))
        evidence_map = {"ev-a": ev_a, "ev-b": ev_b}

        stub = _make_stub(
            preferred_value="Always happens",
            alternative_value="Happens 15% of time",
            preferred_evidence_ids=["ev-a"],
            alternative_evidence_ids=["ev-b"],
        )

        classification = classify_conflict(stub, evidence_map, seed_terms=[])
        assert classification == "genuine_disagreement"


# -- Edge cases ---------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for contradiction resolution."""

    def test_empty_conflict_stubs(self) -> None:
        """Empty input produces empty result."""
        result = resolve_contradictions([], [])
        assert result.total_resolved == 0
        assert result.total_unresolved == 0

    def test_missing_evidence_items(self) -> None:
        """Stubs with unknown evidence IDs don't crash."""
        stub = _make_stub(
            preferred_evidence_ids=["nonexistent-1"],
            alternative_evidence_ids=["nonexistent-2"],
        )

        result = resolve_contradictions([stub], [])
        # Falls through to genuine disagreement (no seed match, no dates)
        assert len(result.genuine_disagreements) == 1

    def test_multiple_stubs_mixed_classifications(self) -> None:
        """Multiple stubs get different classifications."""
        ev_old_doc = _make_evidence("ev-old", category="documents", source_date=datetime(2020, 1, 1, tzinfo=UTC))
        ev_new_doc = _make_evidence("ev-new", category="documents", source_date=datetime(2025, 1, 1, tzinfo=UTC))
        ev_sys = _make_evidence("ev-sys", category="structured_data", source_date=datetime(2025, 6, 1, tzinfo=UTC))
        ev_sme = _make_evidence("ev-sme", category="audio", source_date=datetime(2025, 6, 1, tzinfo=UTC))

        stubs = [
            # Naming variant (typo, edit distance 1 from seed)
            _make_stub(
                preferred_value="Risk Assessment",
                alternative_value="Risk Assesment",
                preferred_evidence_ids=["ev-old"],
                alternative_evidence_ids=["ev-new"],
            ),
            # Temporal shift
            _make_stub(
                preferred_value="New Process",
                alternative_value="Old Process",
                preferred_evidence_ids=["ev-new"],
                alternative_evidence_ids=["ev-old"],
            ),
            # Genuine disagreement
            _make_stub(
                preferred_value="System says always",
                alternative_value="SME says sometimes",
                preferred_evidence_ids=["ev-sys"],
                alternative_evidence_ids=["ev-sme"],
            ),
        ]

        result = resolve_contradictions(
            stubs,
            [ev_old_doc, ev_new_doc, ev_sys, ev_sme],
            seed_terms=["Risk Assessment"],
        )

        assert len(result.naming_resolutions) == 1
        assert len(result.temporal_resolutions) == 1
        assert len(result.genuine_disagreements) == 1

    def test_result_counts_match(self) -> None:
        """total_resolved + total_unresolved = total stubs processed."""
        ev_a = _make_evidence("ev-a", category="documents", source_date=datetime(2020, 1, 1, tzinfo=UTC))
        ev_b = _make_evidence("ev-b", category="documents", source_date=datetime(2025, 1, 1, tzinfo=UTC))

        stubs = [_make_stub(preferred_evidence_ids=["ev-a"], alternative_evidence_ids=["ev-b"]) for _ in range(5)]

        result = resolve_contradictions(stubs, [ev_a, ev_b])

        total = result.total_resolved + result.total_unresolved
        assert total == 5


# -- All six mismatch types handled -------------------------------------------


class TestAllSixMismatchTypes:
    """Verify all six mismatch types from Section 6.10.5 are handled."""

    def test_sequence_mismatch(self) -> None:
        """SEQUENCE_MISMATCH type is processed."""
        severity = compute_severity(MismatchType.SEQUENCE_MISMATCH.value, 0.8, 0.3)
        assert severity > 0.0

    def test_role_mismatch(self) -> None:
        """ROLE_MISMATCH type is processed."""
        severity = compute_severity(MismatchType.ROLE_MISMATCH.value, 0.8, 0.3)
        assert severity > 0.0

    def test_rule_mismatch(self) -> None:
        """RULE_MISMATCH type is processed."""
        severity = compute_severity(MismatchType.RULE_MISMATCH.value, 0.8, 0.3)
        assert severity > 0.0

    def test_existence_mismatch(self) -> None:
        """EXISTENCE_MISMATCH type is processed."""
        severity = compute_severity(MismatchType.EXISTENCE_MISMATCH.value, 0.8, 0.3)
        assert severity > 0.0

    def test_io_mismatch(self) -> None:
        """IO_MISMATCH type is processed."""
        severity = compute_severity(MismatchType.IO_MISMATCH.value, 0.8, 0.3)
        assert severity > 0.0

    def test_control_gap(self) -> None:
        """CONTROL_GAP type is processed."""
        severity = compute_severity(MismatchType.CONTROL_GAP.value, 0.8, 0.3)
        assert severity > 0.0
