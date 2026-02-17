"""Tests for contradiction detection and resolution (LCD Step 5)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, PropertyMock

from src.core.models import CorroborationLevel
from src.pov.consensus import ConsensusElement
from src.pov.contradiction import (
    _compute_source_priority,
    detect_contradictions,
)
from src.pov.triangulation import TriangulatedElement
from src.semantic.entity_extraction import EntityType, ExtractedEntity


def _make_entity(
    name: str = "Test",
    entity_type: str = EntityType.ACTIVITY,
) -> ExtractedEntity:
    return ExtractedEntity(
        id=f"ent_{name.lower().replace(' ', '_')}",
        entity_type=entity_type,
        name=name,
        confidence=0.7,
    )


def _make_evidence_item(
    evidence_id: str | None = None,
    category: str = "documents",
    quality_score: float = 0.7,
    freshness_score: float = 0.8,
    reliability_score: float = 0.75,
):
    item = MagicMock()
    item.id = uuid.UUID(evidence_id) if evidence_id else uuid.uuid4()
    item.category = category
    item.freshness_score = freshness_score
    item.reliability_score = reliability_score
    item.completeness_score = 0.6
    item.consistency_score = 0.65
    type(item).quality_score = PropertyMock(return_value=quality_score)
    return item


def _make_consensus(
    entity: ExtractedEntity,
    evidence_ids: list[str] | None = None,
    weighted_vote_score: float = 0.75,
) -> ConsensusElement:
    ev_ids = evidence_ids or []
    tri = TriangulatedElement(
        entity=entity,
        source_count=len(ev_ids),
        total_sources=5,
        triangulation_score=0.5,
        corroboration_level=CorroborationLevel.MODERATELY,
        evidence_ids=ev_ids,
    )
    return ConsensusElement(
        triangulated=tri,
        weighted_vote_score=weighted_vote_score,
        max_weight=0.85,
        contributing_categories=set(),
    )


class TestComputeSourcePriority:
    """Tests for _compute_source_priority."""

    def test_high_quality_structured_data(self):
        item = _make_evidence_item(
            category="structured_data",
            quality_score=0.9,
            freshness_score=0.95,
        )
        score = _compute_source_priority(item)
        # 1.0 * 0.4 + 0.9 * 0.3 + 0.95 * 0.3 = 0.4 + 0.27 + 0.285 = 0.955
        assert score > 0.9

    def test_low_quality_old_evidence(self):
        item = _make_evidence_item(
            category="job_aids_edge_cases",
            quality_score=0.2,
            freshness_score=0.1,
        )
        score = _compute_source_priority(item)
        # 0.30 * 0.4 + 0.2 * 0.3 + 0.1 * 0.3 = 0.12 + 0.06 + 0.03 = 0.21
        assert score < 0.3


class TestDetectContradictions:
    """Tests for the detect_contradictions function."""

    def test_no_contradictions_single_element(self):
        entity = _make_entity("Process Invoice")
        ev_id = str(uuid.uuid4())
        item = _make_evidence_item(ev_id)
        consensus = _make_consensus(entity, evidence_ids=[ev_id])

        result = detect_contradictions([consensus], [item])

        assert len(result) == 0

    def test_quality_divergence_detected(self):
        """Elements with large quality score differences across sources."""
        entity = _make_entity("Review Contract")
        ev_id1 = str(uuid.uuid4())
        ev_id2 = str(uuid.uuid4())
        item1 = _make_evidence_item(ev_id1, quality_score=0.95)
        item2 = _make_evidence_item(ev_id2, quality_score=0.20)
        consensus = _make_consensus(entity, evidence_ids=[ev_id1, ev_id2])

        result = detect_contradictions([consensus], [item1, item2])

        # Should detect quality divergence (0.95 - 0.20 = 0.75 > 0.4 threshold)
        quality_contradictions = [c for c in result if c.field_name == "quality_divergence"]
        assert len(quality_contradictions) == 1
        assert "quality_divergence" in quality_contradictions[0].field_name

    def test_no_quality_divergence_small_difference(self):
        """No contradiction when quality scores are similar."""
        entity = _make_entity("Submit Form")
        ev_id1 = str(uuid.uuid4())
        ev_id2 = str(uuid.uuid4())
        item1 = _make_evidence_item(ev_id1, quality_score=0.70)
        item2 = _make_evidence_item(ev_id2, quality_score=0.80)
        consensus = _make_consensus(entity, evidence_ids=[ev_id1, ev_id2])

        result = detect_contradictions([consensus], [item1, item2])

        quality_contradictions = [c for c in result if c.field_name == "quality_divergence"]
        assert len(quality_contradictions) == 0

    def test_contradiction_has_resolution(self):
        """Detected contradictions include resolution information."""
        entity = _make_entity("Approve Purchase")
        ev_id1 = str(uuid.uuid4())
        ev_id2 = str(uuid.uuid4())
        item1 = _make_evidence_item(ev_id1, quality_score=0.95)
        item2 = _make_evidence_item(ev_id2, quality_score=0.10)
        consensus = _make_consensus(entity, evidence_ids=[ev_id1, ev_id2])

        result = detect_contradictions([consensus], [item1, item2])

        quality_contradictions = [c for c in result if c.field_name == "quality_divergence"]
        assert len(quality_contradictions) == 1
        c = quality_contradictions[0]
        assert c.resolution_value is not None
        assert c.resolution_reason is not None
        assert len(c.evidence_ids) == 2

    def test_empty_input(self):
        result = detect_contradictions([], [])
        assert result == []

    def test_single_source_no_contradiction(self):
        """Single source element cannot have quality divergence."""
        entity = _make_entity("Solo Task")
        ev_id = str(uuid.uuid4())
        item = _make_evidence_item(ev_id)
        consensus = _make_consensus(entity, evidence_ids=[ev_id])

        result = detect_contradictions([consensus], [item])

        quality_contradictions = [c for c in result if c.field_name == "quality_divergence"]
        assert len(quality_contradictions) == 0
