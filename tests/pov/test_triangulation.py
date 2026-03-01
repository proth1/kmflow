"""Tests for cross-source triangulation (Consensus Step 3)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from src.core.models import CorroborationLevel
from src.pov.triangulation import (
    _compute_triangulation_score,
    _determine_corroboration,
    triangulate_elements,
)
from src.semantic.entity_extraction import EntityType, ExtractedEntity


def _make_entity(name: str = "Test Entity", entity_type: str = EntityType.ACTIVITY) -> ExtractedEntity:
    """Create a test entity."""
    return ExtractedEntity(
        id=f"ent_{name.lower().replace(' ', '_')}",
        entity_type=entity_type,
        name=name,
        confidence=0.7,
    )


def _make_evidence_item(evidence_id: str | None = None):
    """Create a mock evidence item."""
    item = MagicMock()
    item.id = uuid.UUID(evidence_id) if evidence_id else uuid.uuid4()
    item.category = "documents"
    return item


class TestComputeTriangulationScore:
    """Tests for _compute_triangulation_score."""

    def test_zero_sources(self):
        assert _compute_triangulation_score(0, 5) == 0.0

    def test_zero_total(self):
        assert _compute_triangulation_score(3, 0) == 0.0

    def test_single_source(self):
        score = _compute_triangulation_score(1, 5)
        assert 0.0 < score < 0.5
        # 1/5 = 0.2, no multi-source bonus
        assert abs(score - 0.2) < 0.01

    def test_two_sources(self):
        score = _compute_triangulation_score(2, 5)
        # 2/5 = 0.4 + 0.05 bonus = 0.45
        assert abs(score - 0.45) < 0.01

    def test_three_plus_sources(self):
        score = _compute_triangulation_score(3, 5)
        # 3/5 = 0.6 + 0.15 bonus = 0.75
        assert abs(score - 0.75) < 0.01

    def test_all_sources(self):
        score = _compute_triangulation_score(5, 5)
        # 5/5 = 1.0 + 0.15 bonus = capped at 1.0
        assert score == 1.0

    def test_score_capped_at_one(self):
        score = _compute_triangulation_score(10, 5)
        assert score <= 1.0


class TestDetermineCorroboration:
    """Tests for _determine_corroboration."""

    def test_strongly_corroborated(self):
        assert _determine_corroboration(0.75) == CorroborationLevel.STRONGLY

    def test_moderately_corroborated(self):
        assert _determine_corroboration(0.50) == CorroborationLevel.MODERATELY

    def test_weakly_corroborated(self):
        assert _determine_corroboration(0.20) == CorroborationLevel.WEAKLY

    def test_boundary_strongly(self):
        assert _determine_corroboration(0.70) == CorroborationLevel.STRONGLY

    def test_boundary_moderately(self):
        assert _determine_corroboration(0.40) == CorroborationLevel.MODERATELY

    def test_zero_score(self):
        assert _determine_corroboration(0.0) == CorroborationLevel.WEAKLY


class TestTriangulateElements:
    """Tests for the triangulate_elements function."""

    def test_triangulate_single_entity_single_source(self):
        entity = _make_entity("Approve Invoice")
        ev_id = str(uuid.uuid4())
        items = [_make_evidence_item(ev_id)]

        result = triangulate_elements(
            entities=[entity],
            entity_to_evidence={entity.id: [ev_id]},
            evidence_items=items,
        )

        assert len(result) == 1
        assert result[0].source_count == 1
        assert result[0].total_sources == 1
        assert result[0].corroboration_level in (
            CorroborationLevel.STRONGLY,
            CorroborationLevel.MODERATELY,
            CorroborationLevel.WEAKLY,
        )

    def test_triangulate_multi_source_entity(self):
        entity = _make_entity("Submit Request")
        ev_ids = [str(uuid.uuid4()) for _ in range(3)]
        items = [_make_evidence_item(eid) for eid in ev_ids]

        result = triangulate_elements(
            entities=[entity],
            entity_to_evidence={entity.id: ev_ids},
            evidence_items=items,
        )

        assert len(result) == 1
        assert result[0].source_count == 3
        assert result[0].triangulation_score > 0.0
        assert result[0].corroboration_level == CorroborationLevel.STRONGLY

    def test_triangulate_entity_no_evidence(self):
        entity = _make_entity("Orphaned Task")
        items = [_make_evidence_item()]

        result = triangulate_elements(
            entities=[entity],
            entity_to_evidence={},
            evidence_items=items,
        )

        assert len(result) == 1
        assert result[0].source_count == 0
        assert result[0].triangulation_score == 0.0
        assert result[0].corroboration_level == CorroborationLevel.WEAKLY

    def test_triangulate_multiple_entities(self):
        e1 = _make_entity("Task A")
        e2 = _make_entity("Task B")
        ev1 = str(uuid.uuid4())
        ev2 = str(uuid.uuid4())
        ev3 = str(uuid.uuid4())
        items = [_make_evidence_item(eid) for eid in [ev1, ev2, ev3]]

        result = triangulate_elements(
            entities=[e1, e2],
            entity_to_evidence={
                e1.id: [ev1, ev2, ev3],
                e2.id: [ev1],
            },
            evidence_items=items,
        )

        assert len(result) == 2
        # e1 has 3 sources, e2 has 1
        e1_result = [r for r in result if r.entity.name == "Task A"][0]
        e2_result = [r for r in result if r.entity.name == "Task B"][0]
        assert e1_result.triangulation_score > e2_result.triangulation_score

    def test_triangulate_preserves_evidence_ids(self):
        entity = _make_entity("Review Document")
        ev_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        items = [_make_evidence_item(eid) for eid in ev_ids]

        result = triangulate_elements(
            entities=[entity],
            entity_to_evidence={entity.id: ev_ids},
            evidence_items=items,
        )

        assert set(result[0].evidence_ids) == set(ev_ids)

    def test_triangulate_empty_input(self):
        result = triangulate_elements(
            entities=[],
            entity_to_evidence={},
            evidence_items=[],
        )
        assert result == []
