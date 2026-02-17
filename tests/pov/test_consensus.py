"""Tests for consensus building (LCD Step 4)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from src.core.models import CorroborationLevel
from src.pov.consensus import ConsensusElement, build_consensus
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
):
    item = MagicMock()
    item.id = uuid.UUID(evidence_id) if evidence_id else uuid.uuid4()
    item.category = category
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

    def test_consensus_single_element_single_source(self):
        entity = _make_entity("Submit Request")
        ev_id = str(uuid.uuid4())
        item = _make_evidence_item(ev_id, category="documents")
        tri = _make_triangulated(entity, evidence_ids=[ev_id])

        result = build_consensus([tri], [item])

        assert len(result) == 1
        assert isinstance(result[0], ConsensusElement)
        # documents weight = 0.75
        assert abs(result[0].weighted_vote_score - 0.75) < 0.01

    def test_consensus_higher_weight_for_structured_data(self):
        entity = _make_entity("Process Payment")
        ev_id = str(uuid.uuid4())
        item = _make_evidence_item(ev_id, category="structured_data")
        tri = _make_triangulated(entity, evidence_ids=[ev_id])

        result = build_consensus([tri], [item])

        assert len(result) == 1
        # structured_data weight = 1.0
        assert abs(result[0].weighted_vote_score - 1.0) < 0.01

    def test_consensus_multiple_sources_averaged(self):
        entity = _make_entity("Review Invoice")
        ev_id1 = str(uuid.uuid4())
        ev_id2 = str(uuid.uuid4())
        item1 = _make_evidence_item(ev_id1, category="structured_data")  # 1.0
        item2 = _make_evidence_item(ev_id2, category="domain_communications")  # 0.50
        tri = _make_triangulated(entity, evidence_ids=[ev_id1, ev_id2], source_count=2)

        result = build_consensus([tri], [item1, item2])

        assert len(result) == 1
        # Average: (1.0 + 0.50) / 2 = 0.75
        assert abs(result[0].weighted_vote_score - 0.75) < 0.01

    def test_consensus_max_weight_tracked(self):
        entity = _make_entity("Approve Contract")
        ev_id1 = str(uuid.uuid4())
        ev_id2 = str(uuid.uuid4())
        item1 = _make_evidence_item(ev_id1, category="bpm_process_models")  # 0.85
        item2 = _make_evidence_item(ev_id2, category="job_aids_edge_cases")  # 0.30
        tri = _make_triangulated(entity, evidence_ids=[ev_id1, ev_id2], source_count=2)

        result = build_consensus([tri], [item1, item2])

        assert result[0].max_weight == 0.85

    def test_consensus_contributing_categories(self):
        entity = _make_entity("Validate Data")
        ev_id1 = str(uuid.uuid4())
        ev_id2 = str(uuid.uuid4())
        item1 = _make_evidence_item(ev_id1, category="structured_data")
        item2 = _make_evidence_item(ev_id2, category="documents")
        tri = _make_triangulated(entity, evidence_ids=[ev_id1, ev_id2], source_count=2)

        result = build_consensus([tri], [item1, item2])

        assert "structured_data" in result[0].contributing_categories
        assert "documents" in result[0].contributing_categories

    def test_consensus_unknown_category_uses_default(self):
        entity = _make_entity("Unknown Source")
        ev_id = str(uuid.uuid4())
        item = _make_evidence_item(ev_id, category="some_unknown_type")
        tri = _make_triangulated(entity, evidence_ids=[ev_id])

        result = build_consensus([tri], [item])

        # Default weight is 0.30
        assert abs(result[0].weighted_vote_score - 0.30) < 0.01

    def test_consensus_empty_input(self):
        result = build_consensus([], [])
        assert result == []

    def test_consensus_no_evidence_ids(self):
        entity = _make_entity("Orphan")
        tri = _make_triangulated(entity, evidence_ids=[])
        tri.source_count = 0

        result = build_consensus([tri], [])

        assert len(result) == 1
        assert result[0].weighted_vote_score == 0.0
