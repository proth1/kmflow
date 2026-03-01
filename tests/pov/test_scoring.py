"""Tests for confidence scoring (Consensus Step 6)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, PropertyMock

from src.core.models import CorroborationLevel
from src.pov.consensus import ConsensusElement
from src.pov.scoring import (
    _compute_agreement,
    _compute_coverage,
    _compute_quality,
    _compute_recency,
    _compute_reliability,
    classify_confidence,
    compute_element_confidence,
    score_all_elements,
)
from src.pov.triangulation import TriangulatedElement
from src.semantic.entity_extraction import EntityType, ExtractedEntity


def _make_entity(name: str = "Test") -> ExtractedEntity:
    return ExtractedEntity(
        id=f"ent_{name.lower().replace(' ', '_')}",
        entity_type=EntityType.ACTIVITY,
        name=name,
        confidence=0.7,
    )


def _make_evidence_item(
    evidence_id: str | None = None,
    quality_score: float = 0.7,
    reliability_score: float = 0.75,
    freshness_score: float = 0.8,
):
    item = MagicMock()
    item.id = uuid.UUID(evidence_id) if evidence_id else uuid.uuid4()
    item.category = "documents"
    type(item).quality_score = PropertyMock(return_value=quality_score)
    item.reliability_score = reliability_score
    item.freshness_score = freshness_score
    return item


def _make_consensus(
    entity: ExtractedEntity,
    evidence_ids: list[str] | None = None,
    source_count: int = 2,
    total_sources: int = 5,
    weighted_vote_score: float = 0.75,
) -> ConsensusElement:
    ev_ids = evidence_ids or [str(uuid.uuid4()) for _ in range(source_count)]
    tri = TriangulatedElement(
        entity=entity,
        source_count=source_count,
        total_sources=total_sources,
        triangulation_score=0.5,
        corroboration_level=CorroborationLevel.MODERATELY,
        evidence_ids=ev_ids,
    )
    return ConsensusElement(
        triangulated=tri,
        weighted_vote_score=weighted_vote_score,
    )


class TestClassifyConfidence:
    """Tests for classify_confidence."""

    def test_very_high(self):
        assert classify_confidence(0.95) == "VERY_HIGH"

    def test_very_high_boundary(self):
        assert classify_confidence(0.90) == "VERY_HIGH"

    def test_high(self):
        assert classify_confidence(0.80) == "HIGH"

    def test_high_boundary(self):
        assert classify_confidence(0.75) == "HIGH"

    def test_medium(self):
        assert classify_confidence(0.60) == "MEDIUM"

    def test_medium_boundary(self):
        assert classify_confidence(0.50) == "MEDIUM"

    def test_low(self):
        assert classify_confidence(0.35) == "LOW"

    def test_low_boundary(self):
        assert classify_confidence(0.25) == "LOW"

    def test_very_low(self):
        assert classify_confidence(0.10) == "VERY_LOW"

    def test_zero(self):
        assert classify_confidence(0.0) == "VERY_LOW"


class TestComputeCoverage:
    """Tests for _compute_coverage."""

    def test_full_coverage(self):
        entity = _make_entity()
        elem = _make_consensus(entity, source_count=5, total_sources=5)
        assert _compute_coverage(elem, 5) == 1.0

    def test_partial_coverage(self):
        entity = _make_entity()
        elem = _make_consensus(entity, source_count=2, total_sources=5)
        assert abs(_compute_coverage(elem, 5) - 0.4) < 0.01

    def test_zero_sources(self):
        entity = _make_entity()
        elem = _make_consensus(entity, source_count=2, total_sources=5)
        assert _compute_coverage(elem, 0) == 0.0


class TestComputeAgreement:
    """Tests for _compute_agreement."""

    def test_agreement_equals_vote_score(self):
        entity = _make_entity()
        elem = _make_consensus(entity, weighted_vote_score=0.85)
        assert _compute_agreement(elem) == 0.85


class TestComputeQuality:
    """Tests for _compute_quality."""

    def test_quality_average(self):
        ev_id1 = str(uuid.uuid4())
        ev_id2 = str(uuid.uuid4())
        item1 = _make_evidence_item(ev_id1, quality_score=0.8)
        item2 = _make_evidence_item(ev_id2, quality_score=0.6)
        evidence_map = {ev_id1: item1, ev_id2: item2}

        entity = _make_entity()
        elem = _make_consensus(entity, evidence_ids=[ev_id1, ev_id2])

        score = _compute_quality(elem, evidence_map)
        assert abs(score - 0.7) < 0.01

    def test_quality_no_evidence(self):
        entity = _make_entity()
        elem = _make_consensus(entity, evidence_ids=[])
        elem.triangulated.evidence_ids = []
        score = _compute_quality(elem, {})
        assert score == 0.0


class TestComputeReliability:
    """Tests for _compute_reliability."""

    def test_reliability_average(self):
        ev_id = str(uuid.uuid4())
        item = _make_evidence_item(ev_id, reliability_score=0.9)
        evidence_map = {ev_id: item}

        entity = _make_entity()
        elem = _make_consensus(entity, evidence_ids=[ev_id], source_count=1)

        score = _compute_reliability(elem, evidence_map)
        assert abs(score - 0.9) < 0.01


class TestComputeRecency:
    """Tests for _compute_recency."""

    def test_recency_average(self):
        ev_id = str(uuid.uuid4())
        item = _make_evidence_item(ev_id, freshness_score=0.95)
        evidence_map = {ev_id: item}

        entity = _make_entity()
        elem = _make_consensus(entity, evidence_ids=[ev_id], source_count=1)

        score = _compute_recency(elem, evidence_map)
        assert abs(score - 0.95) < 0.01


class TestComputeElementConfidence:
    """Tests for compute_element_confidence."""

    def test_confidence_within_bounds(self):
        ev_id = str(uuid.uuid4())
        item = _make_evidence_item(ev_id)
        entity = _make_entity()
        elem = _make_consensus(entity, evidence_ids=[ev_id], source_count=1, total_sources=3)

        score = compute_element_confidence(elem, [item], 3)

        assert 0.0 <= score <= 1.0

    def test_higher_evidence_means_higher_confidence(self):
        """More/better evidence should yield higher confidence."""
        ev_ids_few = [str(uuid.uuid4())]
        ev_ids_many = [str(uuid.uuid4()) for _ in range(5)]
        items = [
            _make_evidence_item(eid, quality_score=0.9, reliability_score=0.9, freshness_score=0.9)
            for eid in ev_ids_many
        ]

        entity = _make_entity()
        elem_few = _make_consensus(entity, evidence_ids=ev_ids_few, source_count=1, total_sources=5)
        elem_many = _make_consensus(
            entity,
            evidence_ids=ev_ids_many,
            source_count=5,
            total_sources=5,
            weighted_vote_score=0.95,
        )

        score_few = compute_element_confidence(elem_few, items[:1], 5)
        score_many = compute_element_confidence(elem_many, items, 5)

        assert score_many > score_few


class TestScoreAllElements:
    """Tests for score_all_elements."""

    def test_scores_all_elements(self):
        ev_id = str(uuid.uuid4())
        item = _make_evidence_item(ev_id)
        entity1 = _make_entity("Task A")
        entity2 = _make_entity("Task B")
        elem1 = _make_consensus(entity1, evidence_ids=[ev_id], source_count=1)
        elem2 = _make_consensus(entity2, evidence_ids=[ev_id], source_count=1)

        result = score_all_elements([elem1, elem2], [item])

        assert len(result) == 2
        for _elem, score, level in result:
            assert 0.0 <= score <= 1.0
            assert level in ("VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW")

    def test_empty_input(self):
        result = score_all_elements([], [])
        assert result == []
