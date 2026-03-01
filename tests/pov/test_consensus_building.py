"""Tests for Weighted Consensus Building with Consensus Algorithm — Story #310.

Covers all 5 BDD scenarios:
1. Activity included via weighted agreement across source types
2. System data overrides conflicting job aid
3. Low-weight source activity included with lower confidence (consensus inclusivity)
4. Recency bias breaks ties between conflicting sources of equal weight
5. Multiple process variants annotated in output
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from src.core.models import EvidenceCategory, EvidenceItem
from src.pov.consensus import (
    ConflictStub,
    ConsensusResult,
    build_consensus,
    compute_recency_factor,
    get_weight_map,
)
from src.pov.constants import EVIDENCE_TYPE_WEIGHTS
from src.pov.triangulation import TriangulatedElement
from src.semantic.entity_extraction import EntityType, ExtractedEntity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(name: str, entity_type: str = "activity") -> ExtractedEntity:
    """Create a test ExtractedEntity."""
    return ExtractedEntity(
        id=str(uuid.uuid4()),
        name=name,
        entity_type=EntityType(entity_type),
        confidence=0.8,
    )


def _make_evidence(
    category: EvidenceCategory,
    source_date: datetime | None = None,
    quality_score: float = 0.7,
    freshness_score: float = 0.7,
) -> MagicMock:
    """Create a mock EvidenceItem with required attributes."""
    item = MagicMock(spec=EvidenceItem)
    item.id = uuid.uuid4()
    item.category = category
    item.source_date = source_date
    item.quality_score = quality_score
    item.freshness_score = freshness_score
    return item


def _make_triangulated(
    name: str,
    evidence_ids: list[str],
    total_sources: int = 10,
    entity_type: str = "activity",
) -> TriangulatedElement:
    """Create a TriangulatedElement for testing."""
    entity = _make_entity(name, entity_type)
    source_count = len(evidence_ids)
    score = source_count / total_sources if total_sources > 0 else 0.0
    return TriangulatedElement(
        entity=entity,
        source_count=source_count,
        total_sources=total_sources,
        triangulation_score=score,
        evidence_ids=evidence_ids,
    )


# ---------------------------------------------------------------------------
# BDD Scenario 1: Activity included via weighted agreement across source types
# ---------------------------------------------------------------------------


class TestBDDScenario1WeightedAgreement:
    """Given 3 evidence sources all assert Activity X exists
    And Source A is a system event log (weight: 0.9+)
    And Source B is a process document (weight: ~0.75)
    And Source C is an interview transcript (weight: ~0.5)
    When consensus building runs for Activity X
    Then Activity X is included in the consensus process model
    And its composite confidence score reflects the weighted mean of all three sources
    And the confidence is higher than if only interview sources had contributed.
    """

    def test_activity_included_in_consensus(self) -> None:
        """Activity with multi-source evidence is included."""
        ev_system = _make_evidence(EvidenceCategory.STRUCTURED_DATA)
        ev_doc = _make_evidence(EvidenceCategory.DOCUMENTS)
        ev_comms = _make_evidence(EvidenceCategory.DOMAIN_COMMUNICATIONS)

        tri = _make_triangulated(
            "Activity X",
            [str(ev_system.id), str(ev_doc.id), str(ev_comms.id)],
            total_sources=3,
        )

        result = build_consensus([tri], [ev_system, ev_doc, ev_comms])
        assert len(result.elements) == 1
        assert result.elements[0].triangulated.entity.name == "Activity X"

    def test_composite_score_reflects_weighted_mean(self) -> None:
        """Score is weighted average of source weights, not flat average."""
        ev_system = _make_evidence(EvidenceCategory.STRUCTURED_DATA)
        ev_doc = _make_evidence(EvidenceCategory.DOCUMENTS)
        ev_comms = _make_evidence(EvidenceCategory.DOMAIN_COMMUNICATIONS)

        tri = _make_triangulated(
            "Activity X",
            [str(ev_system.id), str(ev_doc.id), str(ev_comms.id)],
        )

        result = build_consensus([tri], [ev_system, ev_doc, ev_comms])
        score = result.elements[0].weighted_vote_score

        # Score should be > 0.5 because system data (1.0) and docs (0.75) pull it up
        assert score > 0.5

    def test_higher_weight_sources_increase_confidence(self) -> None:
        """Multi-source with system data has higher score than interview-only."""
        # With system data
        ev_system = _make_evidence(EvidenceCategory.STRUCTURED_DATA)
        ev_doc = _make_evidence(EvidenceCategory.DOCUMENTS)
        tri_high = _make_triangulated(
            "Activity X",
            [str(ev_system.id), str(ev_doc.id)],
        )
        result_high = build_consensus([tri_high], [ev_system, ev_doc])

        # Interview-only
        ev_interview1 = _make_evidence(EvidenceCategory.DOMAIN_COMMUNICATIONS)
        ev_interview2 = _make_evidence(EvidenceCategory.DOMAIN_COMMUNICATIONS)
        tri_low = _make_triangulated(
            "Activity X",
            [str(ev_interview1.id), str(ev_interview2.id)],
        )
        result_low = build_consensus([tri_low], [ev_interview1, ev_interview2])

        assert result_high.elements[0].weighted_vote_score > result_low.elements[0].weighted_vote_score

    def test_contributing_categories_tracked(self) -> None:
        """Contributing evidence categories are recorded."""
        ev_system = _make_evidence(EvidenceCategory.STRUCTURED_DATA)
        ev_doc = _make_evidence(EvidenceCategory.DOCUMENTS)

        tri = _make_triangulated(
            "Activity X",
            [str(ev_system.id), str(ev_doc.id)],
        )

        result = build_consensus([tri], [ev_system, ev_doc])
        cats = result.elements[0].contributing_categories
        assert "structured_data" in cats
        assert "documents" in cats

    def test_returns_consensus_result_type(self) -> None:
        """build_consensus returns a ConsensusResult dataclass."""
        ev = _make_evidence(EvidenceCategory.DOCUMENTS)
        tri = _make_triangulated("Activity X", [str(ev.id)])
        result = build_consensus([tri], [ev])
        assert isinstance(result, ConsensusResult)
        assert hasattr(result, "elements")
        assert hasattr(result, "variants")
        assert hasattr(result, "conflict_stubs")


# ---------------------------------------------------------------------------
# BDD Scenario 2: System data overrides conflicting job aid
# ---------------------------------------------------------------------------


class TestBDDScenario2SystemOverride:
    """Given system data asserts sequence X -> Y (weight: ~1.0)
    And a job aid asserts reverse Y -> X (weight: ~0.3)
    When consensus building encounters the sequence conflict
    Then X -> Y is accepted as the primary consensus path
    And Y -> X is preserved as a ConflictStub.
    """

    def test_system_data_higher_weight_than_job_aid(self) -> None:
        """System data weight exceeds job aid weight."""
        system_weight = EVIDENCE_TYPE_WEIGHTS.get("structured_data", 0)
        job_aid_weight = EVIDENCE_TYPE_WEIGHTS.get("job_aids_edge_cases", 0)
        assert system_weight > job_aid_weight
        assert system_weight >= 0.9
        assert job_aid_weight <= 0.3

    def test_higher_weight_source_has_higher_consensus_score(self) -> None:
        """Element backed by system data scores higher than job aid backed."""
        ev_system = _make_evidence(EvidenceCategory.STRUCTURED_DATA)
        ev_jobaid = _make_evidence(EvidenceCategory.JOB_AIDS_EDGE_CASES)

        tri_system = _make_triangulated("X -> Y", [str(ev_system.id)])
        tri_jobaid = _make_triangulated("Y -> X", [str(ev_jobaid.id)])

        result = build_consensus([tri_system, tri_jobaid], [ev_system, ev_jobaid])
        system_elem = result.elements[0]
        jobaid_elem = result.elements[1]

        assert system_elem.weighted_vote_score > jobaid_elem.weighted_vote_score

    def test_both_paths_included_consensus_inclusivity(self) -> None:
        """Both paths are included in the consensus (consensus inclusivity)."""
        ev_system = _make_evidence(EvidenceCategory.STRUCTURED_DATA)
        ev_jobaid = _make_evidence(EvidenceCategory.JOB_AIDS_EDGE_CASES)

        tri_system = _make_triangulated("X -> Y", [str(ev_system.id)])
        tri_jobaid = _make_triangulated("Y -> X", [str(ev_jobaid.id)])

        result = build_consensus([tri_system, tri_jobaid], [ev_system, ev_jobaid])
        assert len(result.elements) == 2

    def test_max_weight_reflects_source_type(self) -> None:
        """max_weight on consensus element reflects the evidence type weight."""
        ev_system = _make_evidence(EvidenceCategory.STRUCTURED_DATA)
        tri = _make_triangulated("X -> Y", [str(ev_system.id)])
        result = build_consensus([tri], [ev_system])
        assert result.elements[0].max_weight >= 0.9


# ---------------------------------------------------------------------------
# BDD Scenario 3: Low-weight source activity included with lower confidence
# ---------------------------------------------------------------------------


class TestBDDScenario3LowWeightInclusion:
    """Given Activity 'Manual Override Step' is only in job aids (weight: 0.3)
    And no other evidence source mentions this activity
    When consensus building runs
    Then 'Manual Override Step' is included (consensus inclusivity)
    And its source_reliability is ~0.3
    And its brightness_hint is 'dim' or 'dark'.
    """

    def test_single_job_aid_activity_included(self) -> None:
        """Activity from only job aids is still included in consensus."""
        ev_jobaid = _make_evidence(EvidenceCategory.JOB_AIDS_EDGE_CASES)
        tri = _make_triangulated("Manual Override Step", [str(ev_jobaid.id)])

        result = build_consensus([tri], [ev_jobaid])
        assert len(result.elements) == 1
        assert result.elements[0].triangulated.entity.name == "Manual Override Step"

    def test_source_reliability_reflects_low_weight(self) -> None:
        """Source reliability is low for job-aid-only evidence."""
        ev_jobaid = _make_evidence(EvidenceCategory.JOB_AIDS_EDGE_CASES)
        tri = _make_triangulated("Manual Override Step", [str(ev_jobaid.id)])

        result = build_consensus([tri], [ev_jobaid])
        assert result.elements[0].source_reliability <= 0.4

    def test_brightness_hint_is_dim_or_dark(self) -> None:
        """Low-weight-only elements are classified as dim or dark."""
        ev_jobaid = _make_evidence(EvidenceCategory.JOB_AIDS_EDGE_CASES)
        tri = _make_triangulated("Manual Override Step", [str(ev_jobaid.id)])

        result = build_consensus([tri], [ev_jobaid])
        assert result.elements[0].brightness_hint in ("dim", "dark")

    def test_low_weight_scores_lower_than_high_weight(self) -> None:
        """Job-aid-only element scores lower than system-data element."""
        ev_jobaid = _make_evidence(EvidenceCategory.JOB_AIDS_EDGE_CASES)
        ev_system = _make_evidence(EvidenceCategory.STRUCTURED_DATA)

        tri_low = _make_triangulated("Manual Override Step", [str(ev_jobaid.id)])
        tri_high = _make_triangulated("System Activity", [str(ev_system.id)])

        result = build_consensus([tri_low, tri_high], [ev_jobaid, ev_system])
        low_score = result.elements[0].weighted_vote_score
        high_score = result.elements[1].weighted_vote_score

        assert high_score > low_score

    def test_empty_evidence_gives_zero_score(self) -> None:
        """Element with no evidence IDs gets zero score."""
        tri = _make_triangulated("Phantom", [], total_sources=10)
        result = build_consensus([tri], [])
        assert result.elements[0].weighted_vote_score == 0.0


# ---------------------------------------------------------------------------
# BDD Scenario 4: Recency bias breaks ties between equal-weight sources
# ---------------------------------------------------------------------------


class TestBDDScenario4RecencyBias:
    """Given two sources of equal type (both process documents, weight: 0.75)
    And Source A (dated 2023) asserts Rule P
    And Source B (dated 2025) asserts Rule Q
    When consensus building applies recency bias
    Then the newer source (B) has a higher adjusted weight.
    """

    def test_recency_factor_recent_is_higher(self) -> None:
        """Recent evidence has a higher recency factor than old evidence."""
        now = datetime.now(tz=UTC)
        recent = compute_recency_factor(now - timedelta(days=30))
        old = compute_recency_factor(now - timedelta(days=365 * 3))
        assert recent > old

    def test_recency_factor_undated_is_neutral(self) -> None:
        """Undated evidence returns 0.5 (neutral)."""
        assert compute_recency_factor(None) == 0.5

    def test_recency_factor_future_date_is_one(self) -> None:
        """Future-dated evidence returns 1.0."""
        future = datetime.now(tz=UTC) + timedelta(days=100)
        assert compute_recency_factor(future) == 1.0

    def test_newer_same_weight_source_scores_higher(self) -> None:
        """Newer evidence of same type scores higher due to recency bias."""
        now = datetime.now(tz=UTC)

        ev_old = _make_evidence(
            EvidenceCategory.DOCUMENTS,
            source_date=now - timedelta(days=365 * 3),
        )
        ev_new = _make_evidence(
            EvidenceCategory.DOCUMENTS,
            source_date=now - timedelta(days=30),
        )

        tri_old = _make_triangulated("Rule P", [str(ev_old.id)])
        tri_new = _make_triangulated("Rule Q", [str(ev_new.id)])

        result = build_consensus([tri_old, tri_new], [ev_old, ev_new])
        old_score = result.elements[0].weighted_vote_score
        new_score = result.elements[1].weighted_vote_score

        assert new_score > old_score

    def test_recency_decay_exponential(self) -> None:
        """Recency decay is exponential with ~50% at half-life."""
        now = datetime.now(tz=UTC)
        at_half_life = compute_recency_factor(
            now - timedelta(days=365.25 * 3),  # 3 years = default half-life
            reference_date=now,
        )
        # Should be approximately 0.5 (within tolerance for floating point)
        assert 0.4 <= at_half_life <= 0.6

    def test_recency_factor_zero_age_is_one(self) -> None:
        """Evidence dated today has recency factor of 1.0."""
        now = datetime.now(tz=UTC)
        assert compute_recency_factor(now, reference_date=now) == 1.0

    def test_both_conflicting_sources_included(self) -> None:
        """Both conflicting sources remain in inclusive consensus."""
        now = datetime.now(tz=UTC)
        ev_old = _make_evidence(EvidenceCategory.DOCUMENTS, source_date=now - timedelta(days=1000))
        ev_new = _make_evidence(EvidenceCategory.DOCUMENTS, source_date=now - timedelta(days=30))

        tri_old = _make_triangulated("Rule P", [str(ev_old.id)])
        tri_new = _make_triangulated("Rule Q", [str(ev_new.id)])

        result = build_consensus([tri_old, tri_new], [ev_old, ev_new])
        assert len(result.elements) == 2


# ---------------------------------------------------------------------------
# BDD Scenario 5: Multiple process variants annotated in output
# ---------------------------------------------------------------------------


class TestBDDScenario5VariantDetection:
    """Given evidence supports a standard subprocess path (variant A)
    And evidence also supports an expedited subprocess path (variant B)
    And both variants have evidence_coverage > 0.4
    When consensus building processes the variant evidence
    Then both variant A and variant B are included in the consensus model
    And each is annotated with a variant label and supporting evidence.
    """

    def test_variants_detected_with_sufficient_coverage(self) -> None:
        """Two elements with same name and >0.4 coverage are annotated as variants."""
        ev_items = [_make_evidence(EvidenceCategory.DOCUMENTS) for _ in range(5)]
        ev_ids_a = [str(ev_items[i].id) for i in range(3)]  # 3/5 = 0.6
        ev_ids_b = [str(ev_items[i].id) for i in range(2, 5)]  # 3/5 = 0.6

        tri_a = _make_triangulated("Approval Process", ev_ids_a, total_sources=5)
        tri_b = _make_triangulated("Approval Process", ev_ids_b, total_sources=5)

        result = build_consensus([tri_a, tri_b], ev_items)
        assert len(result.variants) >= 2

    def test_variant_annotations_have_labels(self) -> None:
        """Each variant has a unique label (variant_A, variant_B, etc.)."""
        ev_items = [_make_evidence(EvidenceCategory.DOCUMENTS) for _ in range(5)]
        ev_ids_a = [str(ev_items[i].id) for i in range(3)]
        ev_ids_b = [str(ev_items[i].id) for i in range(2, 5)]

        tri_a = _make_triangulated("Approval Process", ev_ids_a, total_sources=5)
        tri_b = _make_triangulated("Approval Process", ev_ids_b, total_sources=5)

        result = build_consensus([tri_a, tri_b], ev_items)
        labels = {v.variant_label for v in result.variants}
        assert "variant_A" in labels
        assert "variant_B" in labels

    def test_variant_includes_evidence_coverage(self) -> None:
        """Variant annotations include evidence_coverage metric."""
        ev_items = [_make_evidence(EvidenceCategory.DOCUMENTS) for _ in range(5)]
        ev_ids_a = [str(ev_items[i].id) for i in range(3)]
        ev_ids_b = [str(ev_items[i].id) for i in range(2, 5)]

        tri_a = _make_triangulated("Approval Process", ev_ids_a, total_sources=5)
        tri_b = _make_triangulated("Approval Process", ev_ids_b, total_sources=5)

        result = build_consensus([tri_a, tri_b], ev_items)
        for variant in result.variants:
            assert variant.evidence_coverage >= 0.4

    def test_no_variant_below_threshold(self) -> None:
        """Elements with coverage < 0.4 are not annotated as variants."""
        ev_items = [_make_evidence(EvidenceCategory.DOCUMENTS) for _ in range(10)]
        ev_ids_a = [str(ev_items[0].id)]  # 1/10 = 0.1, below threshold
        ev_ids_b = [str(ev_items[1].id)]  # 1/10 = 0.1, below threshold

        tri_a = _make_triangulated("Niche Process", ev_ids_a, total_sources=10)
        tri_b = _make_triangulated("Niche Process", ev_ids_b, total_sources=10)

        result = build_consensus([tri_a, tri_b], ev_items)
        # Should not create variant annotations for low-coverage elements
        niche_variants = [v for v in result.variants if "niche" in v.element_name.lower()]
        assert len(niche_variants) == 0

    def test_neither_variant_discarded(self) -> None:
        """Both variants remain as consensus elements (not discarded)."""
        ev_items = [_make_evidence(EvidenceCategory.DOCUMENTS) for _ in range(4)]
        ev_ids_a = [str(ev_items[i].id) for i in range(2)]
        ev_ids_b = [str(ev_items[i].id) for i in range(2, 4)]

        tri_a = _make_triangulated("Approval Process", ev_ids_a, total_sources=4)
        tri_b = _make_triangulated("Approval Process", ev_ids_b, total_sources=4)

        result = build_consensus([tri_a, tri_b], ev_items)
        assert len(result.elements) == 2


# ---------------------------------------------------------------------------
# Additional consensus builder tests
# ---------------------------------------------------------------------------


class TestEngagementWeightOverrides:
    """Test per-engagement configurable weight maps."""

    def test_default_weight_map_matches_constants(self) -> None:
        """Default weight map matches EVIDENCE_TYPE_WEIGHTS."""
        wm = get_weight_map()
        assert wm == EVIDENCE_TYPE_WEIGHTS

    def test_engagement_override_replaces_default(self) -> None:
        """Per-engagement overrides replace default weights."""
        overrides = {"documents": 0.95, "structured_data": 0.50}
        wm = get_weight_map(overrides)
        assert wm["documents"] == 0.95
        assert wm["structured_data"] == 0.50

    def test_override_clamped_to_0_1(self) -> None:
        """Overrides are clamped to [0.0, 1.0] range."""
        overrides = {"documents": 1.5, "audio": -0.5}
        wm = get_weight_map(overrides)
        assert wm["documents"] == 1.0
        assert wm["audio"] == 0.0

    def test_engagement_weights_used_in_consensus(self) -> None:
        """Custom weights affect consensus scoring."""
        ev_doc = _make_evidence(EvidenceCategory.DOCUMENTS)
        tri = _make_triangulated("Activity Y", [str(ev_doc.id)])

        # Default: documents = 0.75
        result_default = build_consensus([tri], [ev_doc])

        # Override: documents = 0.95
        result_override = build_consensus([tri], [ev_doc], engagement_weights={"documents": 0.95})

        assert result_override.elements[0].weighted_vote_score > result_default.elements[0].weighted_vote_score

    def test_unknown_category_gets_default_weight(self) -> None:
        """Unknown categories get DEFAULT_EVIDENCE_WEIGHT (0.3)."""
        ev = _make_evidence(EvidenceCategory.DOCUMENTS)
        ev.category = "unknown_category"
        tri = _make_triangulated("Activity Z", [str(ev.id)])

        result = build_consensus([tri], [ev])
        # Should use default weight 0.3
        assert result.elements[0].weighted_vote_score > 0.0


class TestConflictStubGeneration:
    """Test ConflictStub forwarding for contradiction resolution."""

    def test_conflict_stub_dataclass_fields(self) -> None:
        """ConflictStub has all required fields."""
        stub = ConflictStub(
            element_name="Activity X",
            disagreement_type="sequence",
            preferred_value="X -> Y",
            alternative_value="Y -> X",
            preferred_evidence_ids=["ev1"],
            alternative_evidence_ids=["ev2"],
            resolution_reason="weight",
        )
        assert stub.element_name == "Activity X"
        assert stub.disagreement_type == "sequence"

    def test_consensus_result_contains_conflict_stubs(self) -> None:
        """ConsensusResult includes conflict_stubs list."""
        ev = _make_evidence(EvidenceCategory.DOCUMENTS)
        tri = _make_triangulated("Activity", [str(ev.id)])
        result = build_consensus([tri], [ev])
        assert isinstance(result.conflict_stubs, list)


class TestConsensusEdgeCases:
    """Edge case and robustness tests."""

    def test_empty_input_returns_empty_result(self) -> None:
        """Empty input produces empty ConsensusResult."""
        result = build_consensus([], [])
        assert len(result.elements) == 0
        assert len(result.variants) == 0
        assert len(result.conflict_stubs) == 0

    def test_single_element_single_source(self) -> None:
        """Single element from single source works correctly."""
        ev = _make_evidence(EvidenceCategory.DOCUMENTS)
        tri = _make_triangulated("Solo Activity", [str(ev.id)])
        result = build_consensus([tri], [ev])
        assert len(result.elements) == 1
        assert result.elements[0].weighted_vote_score > 0.0

    def test_brightness_bright_for_high_score(self) -> None:
        """Element with high score gets brightness_hint='bright'."""
        ev = _make_evidence(EvidenceCategory.STRUCTURED_DATA, source_date=datetime.now(tz=UTC))
        tri = _make_triangulated("High Score Activity", [str(ev.id)])
        result = build_consensus([tri], [ev])
        assert result.elements[0].brightness_hint == "bright"
