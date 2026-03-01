"""Tests for gap detection (Consensus Step 8)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from src.core.models import CorroborationLevel, GapSeverity, GapType
from src.pov.consensus import ConsensusElement
from src.pov.gaps import (
    _detect_missing_category_gaps,
    _detect_single_source_gaps,
    _detect_weak_evidence_gaps,
    detect_gaps,
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


def _make_consensus(
    entity: ExtractedEntity,
    source_count: int = 1,
    evidence_ids: list[str] | None = None,
    weighted_vote_score: float = 0.75,
) -> ConsensusElement:
    ev_ids = evidence_ids or [str(uuid.uuid4()) for _ in range(source_count)]
    tri = TriangulatedElement(
        entity=entity,
        source_count=source_count,
        total_sources=5,
        triangulation_score=0.5,
        corroboration_level=CorroborationLevel.MODERATELY,
        evidence_ids=ev_ids,
    )
    return ConsensusElement(
        triangulated=tri,
        weighted_vote_score=weighted_vote_score,
    )


def _make_evidence_item(category: str = "documents"):
    item = MagicMock()
    item.id = uuid.uuid4()
    item.category = category
    return item


class TestDetectSingleSourceGaps:
    """Tests for _detect_single_source_gaps."""

    def test_single_source_detected(self):
        entity = _make_entity("Lonely Task")
        elem = _make_consensus(entity, source_count=1)

        gaps = _detect_single_source_gaps([elem])

        assert len(gaps) == 1
        assert gaps[0].gap_type == GapType.SINGLE_SOURCE
        assert "Lonely Task" in gaps[0].description

    def test_multi_source_no_gap(self):
        entity = _make_entity("Well Supported")
        elem = _make_consensus(entity, source_count=3)

        gaps = _detect_single_source_gaps([elem])

        assert len(gaps) == 0

    def test_multiple_single_source_elements(self):
        e1 = _make_entity("Task A")
        e2 = _make_entity("Task B")
        elems = [
            _make_consensus(e1, source_count=1),
            _make_consensus(e2, source_count=1),
        ]

        gaps = _detect_single_source_gaps(elems)

        assert len(gaps) == 2

    def test_gap_has_recommendation(self):
        entity = _make_entity("Solo Evidence")
        elem = _make_consensus(entity, source_count=1)

        gaps = _detect_single_source_gaps([elem])

        assert gaps[0].recommendation != ""
        assert "Solo Evidence" in gaps[0].recommendation


class TestDetectWeakEvidenceGaps:
    """Tests for _detect_weak_evidence_gaps."""

    def test_very_low_confidence_detected(self):
        entity = _make_entity("Weak Element")
        elem = _make_consensus(entity)
        scored = [(elem, 0.15, "VERY_LOW")]

        gaps = _detect_weak_evidence_gaps(scored)

        assert len(gaps) == 1
        assert gaps[0].gap_type == GapType.WEAK_EVIDENCE
        assert gaps[0].severity == GapSeverity.HIGH

    def test_low_confidence_detected(self):
        entity = _make_entity("Low Element")
        elem = _make_consensus(entity)
        scored = [(elem, 0.30, "LOW")]

        gaps = _detect_weak_evidence_gaps(scored)

        assert len(gaps) == 1
        assert gaps[0].severity == GapSeverity.MEDIUM

    def test_medium_confidence_no_gap(self):
        entity = _make_entity("OK Element")
        elem = _make_consensus(entity)
        scored = [(elem, 0.60, "MEDIUM")]

        gaps = _detect_weak_evidence_gaps(scored)

        assert len(gaps) == 0

    def test_high_confidence_no_gap(self):
        entity = _make_entity("Strong Element")
        elem = _make_consensus(entity)
        scored = [(elem, 0.85, "HIGH")]

        gaps = _detect_weak_evidence_gaps(scored)

        assert len(gaps) == 0


class TestDetectMissingCategoryGaps:
    """Tests for _detect_missing_category_gaps."""

    def test_all_categories_covered(self):
        """No gaps when all 12 categories have evidence."""
        from src.core.models import EvidenceCategory

        items = [_make_evidence_item(cat.value) for cat in EvidenceCategory]

        gaps = _detect_missing_category_gaps(items)

        assert len(gaps) == 0

    def test_missing_critical_category_high_severity(self):
        items = [_make_evidence_item("images")]

        gaps = _detect_missing_category_gaps(items)

        # Many categories missing, check for critical ones
        critical_gaps = [g for g in gaps if g.severity == GapSeverity.HIGH]
        assert len(critical_gaps) > 0

    def test_no_evidence_all_categories_missing(self):
        gaps = _detect_missing_category_gaps([])

        from src.core.models import EvidenceCategory

        assert len(gaps) == len(EvidenceCategory)


class TestDetectGaps:
    """Tests for the main detect_gaps function."""

    def test_combines_all_gap_types(self):
        entity = _make_entity("Test Task")
        elem = _make_consensus(entity, source_count=1)
        scored = [(elem, 0.20, "VERY_LOW")]
        items = [_make_evidence_item("documents")]

        gaps = detect_gaps([elem], scored, items)

        gap_types = {g.gap_type for g in gaps}
        # Should have at least single-source and weak-evidence gaps
        assert GapType.SINGLE_SOURCE in gap_types
        assert GapType.WEAK_EVIDENCE in gap_types
        # Should also have missing category gaps (only 1 of 12 covered)
        assert GapType.MISSING_DATA in gap_types

    def test_empty_input(self):
        gaps = detect_gaps([], [], [])

        # Should still detect missing categories (all 12 missing)
        from src.core.models import EvidenceCategory

        assert len(gaps) == len(EvidenceCategory)
        assert all(g.gap_type == GapType.MISSING_DATA for g in gaps)
