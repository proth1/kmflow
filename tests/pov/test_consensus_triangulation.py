"""BDD tests for Consensus Step 3: Cross-Source Triangulation Engine.

Story #306: Validate process elements by corroboration across multiple
evidence types with evidence plane classification, coverage/agreement
factors, single-source flagging, and conflict detection.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from src.core.models import CorroborationLevel
from src.pov.constants import CROSS_PLANE_BONUS
from src.pov.triangulation import (
    compute_evidence_agreement,
    compute_evidence_coverage,
    detect_source_conflicts,
    get_evidence_plane,
    triangulate_elements,
)
from src.semantic.entity_extraction import EntityType, ExtractedEntity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(
    name: str = "Test Activity",
    entity_type: EntityType = EntityType.ACTIVITY,
) -> ExtractedEntity:
    entity_id = f"ent_{name.lower().replace(' ', '_')}"
    return ExtractedEntity(
        id=entity_id,
        entity_type=entity_type,
        name=name,
        confidence=0.7,
    )


def _make_evidence_item(
    evidence_id: str | None = None,
    category: str = "documents",
) -> MagicMock:
    item = MagicMock()
    item.id = uuid.UUID(evidence_id) if evidence_id else uuid.uuid4()
    item.category = category
    return item


# ===========================================================================
# Scenario 1: High-coverage activity triangulated across four sources
# ===========================================================================


class TestHighCoverageTriangulation:
    """Given Activity extracted from 4 distinct sources spanning >=2 planes,
    when triangulation runs, evidence_coverage >= 0.8 and element is
    classified as well-corroborated.
    """

    def test_four_sources_high_coverage(self):
        """4 sources across 2+ planes produce high evidence_coverage."""
        entity = _make_entity("Verify Identity")
        ev_ids = [str(uuid.uuid4()) for _ in range(4)]

        # Sources from 3 different planes
        items = [
            _make_evidence_item(ev_ids[0], "structured_data"),  # system_behavioral
            _make_evidence_item(ev_ids[1], "documents"),  # documented_formal
            _make_evidence_item(ev_ids[2], "images"),  # observed_field
            _make_evidence_item(ev_ids[3], "km4work"),  # human_interpretation
        ]

        entity_to_evidence = {entity.id: ev_ids}
        result = triangulate_elements([entity], entity_to_evidence, items)

        assert len(result) == 1
        elem = result[0]
        assert elem.evidence_coverage >= 0.8

    def test_corroboration_matrix_records_four_links(self):
        """Corroboration matrix records 4 supporting source links."""
        entity = _make_entity("Verify Identity")
        ev_ids = [str(uuid.uuid4()) for _ in range(4)]

        items = [
            _make_evidence_item(ev_ids[0], "structured_data"),
            _make_evidence_item(ev_ids[1], "documents"),
            _make_evidence_item(ev_ids[2], "images"),
            _make_evidence_item(ev_ids[3], "km4work"),
        ]

        entity_to_evidence = {entity.id: ev_ids}
        result = triangulate_elements([entity], entity_to_evidence, items)

        elem = result[0]
        assert len(elem.evidence_ids) == 4
        assert elem.source_count == 4

    def test_well_corroborated_classification(self):
        """4 out of 4 sources = strongly corroborated."""
        entity = _make_entity("Verify Identity")
        ev_ids = [str(uuid.uuid4()) for _ in range(4)]

        items = [
            _make_evidence_item(ev_ids[0], "structured_data"),
            _make_evidence_item(ev_ids[1], "documents"),
            _make_evidence_item(ev_ids[2], "images"),
            _make_evidence_item(ev_ids[3], "km4work"),
        ]

        entity_to_evidence = {entity.id: ev_ids}
        result = triangulate_elements([entity], entity_to_evidence, items)

        elem = result[0]
        assert elem.corroboration_level == CorroborationLevel.STRONGLY

    def test_four_planes_supported(self):
        """All 4 evidence planes represented in supporting planes."""
        entity = _make_entity("Verify Identity")
        ev_ids = [str(uuid.uuid4()) for _ in range(4)]

        items = [
            _make_evidence_item(ev_ids[0], "structured_data"),
            _make_evidence_item(ev_ids[1], "documents"),
            _make_evidence_item(ev_ids[2], "images"),
            _make_evidence_item(ev_ids[3], "km4work"),
        ]

        entity_to_evidence = {entity.id: ev_ids}
        result = triangulate_elements([entity], entity_to_evidence, items)

        elem = result[0]
        assert len(elem.supporting_planes) == 4
        assert "system_behavioral" in elem.supporting_planes
        assert "documented_formal" in elem.supporting_planes
        assert "observed_field" in elem.supporting_planes
        assert "human_interpretation" in elem.supporting_planes


# ===========================================================================
# Scenario 2: Single-source activity flagged as low-confidence
# ===========================================================================


class TestSingleSourceFlagging:
    """Given Activity extracted from exactly 1 source, when triangulation
    runs, coverage <= 0.3, single_source = True.
    """

    def test_single_source_low_coverage(self):
        """Single source element has low evidence_coverage."""
        entity = _make_entity("Archive Report")
        ev_id = str(uuid.uuid4())

        items = [
            _make_evidence_item(ev_id, "documents"),
            _make_evidence_item(category="structured_data"),
            _make_evidence_item(category="images"),
            _make_evidence_item(category="km4work"),
        ]

        entity_to_evidence = {entity.id: [ev_id]}
        result = triangulate_elements([entity], entity_to_evidence, items)

        elem = result[0]
        # Only 1 of 4 planes → coverage = 0.25
        assert elem.evidence_coverage <= 0.3

    def test_single_source_flagged(self):
        """Single source element has single_source = True."""
        entity = _make_entity("Archive Report")
        ev_id = str(uuid.uuid4())

        items = [_make_evidence_item(ev_id, "documents")]
        entity_to_evidence = {entity.id: [ev_id]}
        result = triangulate_elements([entity], entity_to_evidence, items)

        elem = result[0]
        assert elem.single_source is True

    def test_multi_source_not_flagged(self):
        """2-source element is not flagged as single_source."""
        entity = _make_entity("Process Invoice")
        ev_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

        items = [
            _make_evidence_item(ev_ids[0], "documents"),
            _make_evidence_item(ev_ids[1], "structured_data"),
        ]

        entity_to_evidence = {entity.id: ev_ids}
        result = triangulate_elements([entity], entity_to_evidence, items)

        elem = result[0]
        assert elem.single_source is False

    def test_weakly_corroborated(self):
        """Single source element is weakly corroborated."""
        entity = _make_entity("Archive Report")
        ev_id = str(uuid.uuid4())

        items = [
            _make_evidence_item(ev_id, "documents"),
            _make_evidence_item(category="structured_data"),
            _make_evidence_item(category="images"),
            _make_evidence_item(category="km4work"),
            _make_evidence_item(category="audio"),
        ]

        entity_to_evidence = {entity.id: [ev_id]}
        result = triangulate_elements([entity], entity_to_evidence, items)

        elem = result[0]
        assert elem.corroboration_level == CorroborationLevel.WEAKLY


# ===========================================================================
# Scenario 3: Cross-plane corroboration boosts agreement score
# ===========================================================================


class TestCrossPlaneCorroboration:
    """Given Activity confirmed by sources from different planes, when
    cross-plane agreement is scored, the factor is higher than same-plane.
    """

    def test_cross_plane_agreement_higher(self):
        """Cross-plane corroboration gives higher agreement than same-plane."""
        # Use partial agreement (2/3) so bonus is visible before cap
        cross_plane_agreement = compute_evidence_agreement(agreeing_count=2, total_mentioning=3, cross_plane=True)
        same_plane_agreement = compute_evidence_agreement(agreeing_count=2, total_mentioning=3, cross_plane=False)
        assert cross_plane_agreement > same_plane_agreement

    def test_cross_plane_bonus_applied(self):
        """Cross-plane bonus adds CROSS_PLANE_BONUS to agreement score."""
        # Use partial agreement so bonus doesn't hit the 1.0 cap
        base = compute_evidence_agreement(2, 3, cross_plane=False)
        boosted = compute_evidence_agreement(2, 3, cross_plane=True)
        assert abs((boosted - base) - CROSS_PLANE_BONUS) < 1e-9

    def test_agreement_capped_at_1(self):
        """Agreement factor cannot exceed 1.0."""
        agreement = compute_evidence_agreement(5, 5, cross_plane=True)
        assert agreement <= 1.0

    def test_two_plane_sources_detected(self):
        """Two sources from different planes detected in triangulation."""
        entity = _make_entity("Risk Assessment")
        ev_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

        items = [
            _make_evidence_item(ev_ids[0], "structured_data"),  # system_behavioral
            _make_evidence_item(ev_ids[1], "documents"),  # documented_formal
        ]

        entity_to_evidence = {entity.id: ev_ids}
        result = triangulate_elements([entity], entity_to_evidence, items)

        elem = result[0]
        assert len(elem.supporting_planes) == 2
        assert "system_behavioral" in elem.supporting_planes
        assert "documented_formal" in elem.supporting_planes

    def test_cross_plane_higher_in_triangulation(self):
        """Cross-plane element has higher agreement than same-plane in actual triangulation."""
        # Cross-plane entity: 2 sources from different planes
        cross_entity = _make_entity("Risk Assessment")
        cross_ev_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

        # Same-plane entity: 2 sources from same plane
        same_entity = _make_entity("Review Policy")
        same_ev_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

        items = [
            _make_evidence_item(cross_ev_ids[0], "structured_data"),
            _make_evidence_item(cross_ev_ids[1], "documents"),
            _make_evidence_item(same_ev_ids[0], "documents"),
            _make_evidence_item(same_ev_ids[1], "bpm_process_models"),
        ]

        entity_to_evidence = {
            cross_entity.id: cross_ev_ids,
            same_entity.id: same_ev_ids,
        }
        result = triangulate_elements([cross_entity, same_entity], entity_to_evidence, items)

        cross_elem = next(r for r in result if r.entity.name == "Risk Assessment")
        same_elem = next(r for r in result if r.entity.name == "Review Policy")

        assert cross_elem.evidence_agreement > same_elem.evidence_agreement


# ===========================================================================
# Scenario 4: Source conflict detected during triangulation
# ===========================================================================


class TestSourceConflictDetection:
    """Given Activity asserted by 2 sources and contradicted by 1, when
    triangulation runs, the conflict is flagged.
    """

    def test_conflict_flagged(self):
        """Element with contradicting source has has_conflict=True."""
        entity = _make_entity("Compliance Check")
        ev_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        contradicting_ev_id = str(uuid.uuid4())

        items = [
            _make_evidence_item(ev_ids[0], "documents"),
            _make_evidence_item(ev_ids[1], "structured_data"),
            _make_evidence_item(contradicting_ev_id, "images"),
        ]

        entity_to_evidence = {entity.id: ev_ids}
        result = triangulate_elements([entity], entity_to_evidence, items)

        # Apply conflict detection
        contradicting = {entity.id: [contradicting_ev_id]}
        result = detect_source_conflicts(result, contradicting)

        elem = result[0]
        assert elem.has_conflict is True

    def test_conflicting_source_recorded(self):
        """Conflicting evidence IDs are recorded on the element."""
        entity = _make_entity("Compliance Check")
        ev_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        contradicting_ev_id = str(uuid.uuid4())

        items = [
            _make_evidence_item(ev_ids[0], "documents"),
            _make_evidence_item(ev_ids[1], "structured_data"),
            _make_evidence_item(contradicting_ev_id, "images"),
        ]

        entity_to_evidence = {entity.id: ev_ids}
        result = triangulate_elements([entity], entity_to_evidence, items)

        contradicting = {entity.id: [contradicting_ev_id]}
        result = detect_source_conflicts(result, contradicting)

        elem = result[0]
        assert contradicting_ev_id in elem.conflicting_evidence_ids

    def test_no_conflict_when_no_contradictions(self):
        """Element without contradicting evidence has has_conflict=False."""
        entity = _make_entity("Process Invoice")
        ev_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

        items = [
            _make_evidence_item(ev_ids[0], "documents"),
            _make_evidence_item(ev_ids[1], "structured_data"),
        ]

        entity_to_evidence = {entity.id: ev_ids}
        result = triangulate_elements([entity], entity_to_evidence, items)

        result = detect_source_conflicts(result, contradicting_evidence=None)

        elem = result[0]
        assert elem.has_conflict is False

    def test_conflict_detection_with_empty_dict(self):
        """Empty contradicting evidence dict does not flag anything."""
        entity = _make_entity("Review Budget")
        ev_id = str(uuid.uuid4())

        items = [_make_evidence_item(ev_id, "documents")]
        entity_to_evidence = {entity.id: [ev_id]}
        result = triangulate_elements([entity], entity_to_evidence, items)

        result = detect_source_conflicts(result, contradicting_evidence={})
        assert result[0].has_conflict is False


# ===========================================================================
# Evidence plane mapping tests
# ===========================================================================


class TestEvidencePlaneMapping:
    """Tests for the get_evidence_plane function."""

    def test_structured_data_is_system_behavioral(self):
        assert get_evidence_plane("structured_data") == "system_behavioral"

    def test_task_mining_is_system_behavioral(self):
        assert get_evidence_plane("task_mining") == "system_behavioral"

    def test_documents_is_documented_formal(self):
        assert get_evidence_plane("documents") == "documented_formal"

    def test_bpm_models_is_documented_formal(self):
        assert get_evidence_plane("bpm_process_models") == "documented_formal"

    def test_images_is_observed_field(self):
        assert get_evidence_plane("images") == "observed_field"

    def test_km4work_is_human_interpretation(self):
        assert get_evidence_plane("km4work") == "human_interpretation"

    def test_unknown_defaults_to_observed_field(self):
        assert get_evidence_plane("unknown_category") == "observed_field"


# ===========================================================================
# Coverage and agreement factor tests
# ===========================================================================


class TestCoverageAndAgreement:
    """Tests for compute_evidence_coverage and compute_evidence_agreement."""

    def test_full_coverage(self):
        """All available planes supported = 1.0."""
        available = {"system_behavioral", "documented_formal"}
        supporting = {"system_behavioral", "documented_formal"}
        assert compute_evidence_coverage(supporting, available) == 1.0

    def test_partial_coverage(self):
        """1 of 4 planes = 0.25."""
        available = {"system_behavioral", "documented_formal", "observed_field", "human_interpretation"}
        supporting = {"documented_formal"}
        assert compute_evidence_coverage(supporting, available) == 0.25

    def test_empty_available_planes(self):
        """No available planes = 0.0."""
        assert compute_evidence_coverage(set(), set()) == 0.0

    def test_agreement_all_agree(self):
        """All sources agree = 1.0 (no cross-plane bonus)."""
        assert compute_evidence_agreement(3, 3, cross_plane=False) == 1.0

    def test_agreement_partial(self):
        """2 of 3 agree = 0.667."""
        agreement = compute_evidence_agreement(2, 3, cross_plane=False)
        assert abs(agreement - 2 / 3) < 0.01

    def test_agreement_no_sources(self):
        """No sources = 0.0."""
        assert compute_evidence_agreement(0, 0) == 0.0


# ===========================================================================
# Edge cases and integration
# ===========================================================================


class TestTriangulationEdgeCases:
    """Edge cases for triangulation."""

    def test_empty_entities(self):
        """Empty entity list produces empty result."""
        result = triangulate_elements([], {}, [])
        assert result == []

    def test_entity_with_no_evidence(self):
        """Entity not in entity_to_evidence gets 0 sources."""
        entity = _make_entity("Orphan Activity")
        items = [_make_evidence_item(category="documents")]
        result = triangulate_elements([entity], {}, items)

        elem = result[0]
        assert elem.source_count == 0
        assert elem.single_source is True
        assert elem.evidence_coverage == 0.0

    def test_multiple_entities_independent(self):
        """Multiple entities triangulated independently."""
        e1 = _make_entity("Activity A")
        e2 = _make_entity("Activity B")
        ev1 = str(uuid.uuid4())
        ev2 = str(uuid.uuid4())
        ev3 = str(uuid.uuid4())

        items = [
            _make_evidence_item(ev1, "documents"),
            _make_evidence_item(ev2, "structured_data"),
            _make_evidence_item(ev3, "images"),
        ]

        entity_to_evidence = {
            e1.id: [ev1, ev2, ev3],  # 3 sources
            e2.id: [ev1],  # 1 source
        }

        result = triangulate_elements([e1, e2], entity_to_evidence, items)

        assert len(result) == 2
        elem_a = next(r for r in result if r.entity.name == "Activity A")
        elem_b = next(r for r in result if r.entity.name == "Activity B")

        assert elem_a.source_count == 3
        assert elem_b.source_count == 1
        assert elem_a.single_source is False
        assert elem_b.single_source is True
        assert elem_a.corroboration_level in (CorroborationLevel.STRONGLY, CorroborationLevel.MODERATELY)
        assert elem_b.corroboration_level == CorroborationLevel.WEAKLY
