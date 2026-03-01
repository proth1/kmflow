"""Tests for consensus building (Consensus Step 4)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from src.core.models import CorroborationLevel
from src.pov.consensus import ConsensusElement, ConsensusResult, build_consensus
from src.pov.triangulation import TriangulatedElement
from src.semantic.entity_extraction import EntityType, ExtractedEntity


def _make_entity(name: str = "Test", entity_type: str = EntityType.ACTIVITY) -> ExtractedEntity:
    return ExtractedEntity(
        id=f"ent_{name.lower().replace(' ', '_')}",
        entity_type=entity_type,
        name=name,
        confidence=0.7,
    )


def _make_evidence_item(
    evidence_id: str | None = None,
    category: str = "documents",
    source_date: object = None,
):
    item = MagicMock()
    item.id = uuid.UUID(evidence_id) if evidence_id else uuid.uuid4()
    item.category = category
    item.source_date = source_date
    return item


def _make_triangulated(
    entity: ExtractedEntity,
    evidence_ids: list[str] | None = None,
    source_count: int = 1,
    total_sources: int = 3,
) -> TriangulatedElement:
    ev_ids = evidence_ids if evidence_ids is not None else [str(uuid.uuid4())]
    return TriangulatedElement(
        entity=entity,
        source_count=source_count,
        total_sources=total_sources,
        triangulation_score=source_count / total_sources,
        corroboration_level=CorroborationLevel.MODERATELY,
        evidence_ids=ev_ids,
    )


class TestBuildConsensus:
    """Tests for the build_consensus function."""

    def test_consensus_returns_consensus_result(self):
        entity = _make_entity("Submit Request")
        ev_id = str(uuid.uuid4())
        item = _make_evidence_item(ev_id, category="documents")
        tri = _make_triangulated(entity, evidence_ids=[ev_id])

        result = build_consensus([tri], [item])

        assert isinstance(result, ConsensusResult)
        assert len(result.elements) == 1
        assert isinstance(result.elements[0], ConsensusElement)

    def test_consensus_single_element_single_source(self):
        entity = _make_entity("Submit Request")
        ev_id = str(uuid.uuid4())
        item = _make_evidence_item(ev_id, category="documents")
        tri = _make_triangulated(entity, evidence_ids=[ev_id])

        result = build_consensus([tri], [item])
        elements = result.elements

        assert len(elements) == 1
        assert isinstance(elements[0], ConsensusElement)
        # documents weight = 0.75, with recency adjustment
        assert elements[0].weighted_vote_score >= 0.52  # min: 0.75 * 0.7
        assert elements[0].weighted_vote_score <= 0.75  # max: 0.75 * 1.0

    def test_consensus_higher_weight_for_structured_data(self):
        entity = _make_entity("Process Payment")
        ev_id = str(uuid.uuid4())
        item = _make_evidence_item(ev_id, category="structured_data")
        tri = _make_triangulated(entity, evidence_ids=[ev_id])

        result = build_consensus([tri], [item])
        elements = result.elements

        assert len(elements) == 1
        # structured_data weight = 1.0, with recency adjustment
        assert elements[0].weighted_vote_score >= 0.70  # min: 1.0 * 0.7
        assert elements[0].weighted_vote_score <= 1.0  # max: 1.0 * 1.0

    def test_consensus_multiple_sources_averaged(self):
        entity = _make_entity("Review Invoice")
        ev_id1 = str(uuid.uuid4())
        ev_id2 = str(uuid.uuid4())
        item1 = _make_evidence_item(ev_id1, category="structured_data")  # 1.0
        item2 = _make_evidence_item(ev_id2, category="domain_communications")  # 0.50
        tri = _make_triangulated(entity, evidence_ids=[ev_id1, ev_id2], source_count=2)

        result = build_consensus([tri], [item1, item2])
        elements = result.elements

        assert len(elements) == 1
        # Average with recency: (1.0 * adj + 0.50 * adj) / 2
        assert elements[0].weighted_vote_score > 0.4
        assert elements[0].weighted_vote_score < 0.85

    def test_consensus_max_weight_tracked(self):
        entity = _make_entity("Approve Contract")
        ev_id1 = str(uuid.uuid4())
        ev_id2 = str(uuid.uuid4())
        item1 = _make_evidence_item(ev_id1, category="bpm_process_models")  # 0.85
        item2 = _make_evidence_item(ev_id2, category="job_aids_edge_cases")  # 0.30
        tri = _make_triangulated(entity, evidence_ids=[ev_id1, ev_id2], source_count=2)

        result = build_consensus([tri], [item1, item2])

        assert result.elements[0].max_weight == 0.85

    def test_consensus_contributing_categories(self):
        entity = _make_entity("Validate Data")
        ev_id1 = str(uuid.uuid4())
        ev_id2 = str(uuid.uuid4())
        item1 = _make_evidence_item(ev_id1, category="structured_data")
        item2 = _make_evidence_item(ev_id2, category="documents")
        tri = _make_triangulated(entity, evidence_ids=[ev_id1, ev_id2], source_count=2)

        result = build_consensus([tri], [item1, item2])

        assert "structured_data" in result.elements[0].contributing_categories
        assert "documents" in result.elements[0].contributing_categories

    def test_consensus_unknown_category_uses_default(self):
        entity = _make_entity("Unknown Source")
        ev_id = str(uuid.uuid4())
        item = _make_evidence_item(ev_id, category="some_unknown_type")
        tri = _make_triangulated(entity, evidence_ids=[ev_id])

        result = build_consensus([tri], [item])

        # Default weight is 0.30, with recency adjustment
        assert result.elements[0].weighted_vote_score >= 0.21  # 0.30 * 0.7
        assert result.elements[0].weighted_vote_score <= 0.30  # 0.30 * 1.0

    def test_consensus_empty_input(self):
        result = build_consensus([], [])
        assert isinstance(result, ConsensusResult)
        assert result.elements == []

    def test_consensus_no_evidence_ids(self):
        entity = _make_entity("Orphan")
        tri = _make_triangulated(entity, evidence_ids=[])
        tri.source_count = 0

        result = build_consensus([tri], [])

        assert len(result.elements) == 1
        assert result.elements[0].weighted_vote_score == 0.0
