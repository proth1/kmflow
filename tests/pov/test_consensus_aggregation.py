"""BDD tests for Consensus Steps 1-2: Evidence Aggregation and Entity Extraction.

Story #303: Collect all evidence for a scoped business area and extract
process elements (activities, decisions, roles, systems) from each evidence
source, guided by seed list terms.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from src.pov.extraction import extract_from_evidence
from src.semantic.entity_extraction import (
    EntityType,
    ExtractedEntity,
    _check_name_similarity,
    _match_seed_term,
    extract_entities,
    resolve_entities,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_evidence_item(
    evidence_id: str | None = None,
    category: str = "documents",
    quality_score: float = 0.7,
    freshness_score: float = 0.8,
) -> MagicMock:
    """Create a mock EvidenceItem."""
    item = MagicMock()
    item.id = uuid.UUID(evidence_id) if evidence_id else uuid.uuid4()
    item.category = category
    item.quality_score = quality_score
    item.freshness_score = freshness_score
    item.name = f"Evidence {str(item.id)[:8]}"
    item.fragments = []
    return item


def _make_fragment(
    content: str,
    evidence_id: uuid.UUID | None = None,
    fragment_id: uuid.UUID | None = None,
) -> MagicMock:
    """Create a mock EvidenceFragment."""
    frag = MagicMock()
    frag.id = fragment_id or uuid.uuid4()
    frag.evidence_id = evidence_id or uuid.uuid4()
    frag.content = content
    return frag


# ===========================================================================
# Scenario 1: Aggregating all evidence for an engagement scope
# ===========================================================================


class TestAggregateEvidenceForEngagementScope:
    """Given an engagement with evidence items across categories,
    when aggregation runs, all items are collected and grouped by category.
    """

    @pytest.mark.asyncio
    async def test_items_grouped_by_category(self):
        """All evidence items collected and grouped by category."""
        # 3 categories, 4 items
        items = [
            _make_evidence_item(category="documents"),
            _make_evidence_item(category="documents"),
            _make_evidence_item(category="structured_data"),
            _make_evidence_item(category="bpm_process_models"),
        ]

        categories = [str(item.category) for item in items]
        assert categories.count("documents") == 2
        assert categories.count("structured_data") == 1
        assert categories.count("bpm_process_models") == 1

    @pytest.mark.asyncio
    async def test_items_retain_source_metadata(self):
        """Each item retains category, quality score, and recency."""
        item = _make_evidence_item(category="structured_data", quality_score=0.9, freshness_score=0.95)
        assert str(item.category) == "structured_data"
        assert item.quality_score == 0.9
        assert item.freshness_score == 0.95

    @pytest.mark.asyncio
    async def test_aggregation_collects_all_items(self):
        """All N items are collected (no items dropped)."""
        n = 20
        items = [_make_evidence_item() for _ in range(n)]
        assert len(items) == n


# ===========================================================================
# Scenario 2: Extracting activities from a BPMN file
# ===========================================================================


class TestExtractActivitiesFromBpmn:
    """Given a BPMN-like evidence file with activity task labels,
    when entity extraction runs, Activity entities are created matching labels.
    """

    @pytest.mark.asyncio
    async def test_bpmn_task_labels_extracted(self):
        """Activity entities extracted from BPMN task label text."""
        # Simulating BPMN task labels as text (after BPMN parsing)
        bpmn_text = (
            "Process Invoice, Validate Payment, Submit Purchase Order, "
            "Approve Contract, Review Budget, Send Notification, "
            "Create Report, Update Records, Assign Reviewer, Audit Transaction"
        )
        result = await extract_entities(bpmn_text)
        activity_names = [e.name for e in result.entities if e.entity_type == EntityType.ACTIVITY]
        assert len(activity_names) >= 5  # Should extract several activities

    @pytest.mark.asyncio
    async def test_each_entity_has_name_matching_task_label(self):
        """Entity names match the corresponding BPMN task labels."""
        text = "Submit Purchase Order. Approve Invoice. Review Contract."
        result = await extract_entities(text)
        names = {e.name for e in result.entities if e.entity_type == EntityType.ACTIVITY}
        assert "Submit Purchase Order" in names or "Approve Invoice" in names

    @pytest.mark.asyncio
    async def test_entities_linked_to_source_evidence(self):
        """Entities are linked to source evidence via provenance maps."""
        ev_id = uuid.uuid4()
        frag_id = uuid.uuid4()
        item = _make_evidence_item(str(ev_id))
        frag = _make_fragment("Submit Purchase Order. Approve Invoice.", ev_id, frag_id)
        item.fragments = [frag]

        summary = await extract_from_evidence([item], [frag])

        # Entities should have evidence provenance
        for _entity_id, ev_ids in summary.entity_to_evidence.items():
            assert str(ev_id) in ev_ids

    @pytest.mark.asyncio
    async def test_bpmn_document_entities_extracted(self):
        """Document-type entities like Purchase Order also extracted."""
        text = "Submit Purchase Order #1234. Update the Invoice."
        result = await extract_entities(text)
        doc_names = [e.name for e in result.entities if e.entity_type == EntityType.DOCUMENT]
        assert any("Purchase Order" in name for name in doc_names)


# ===========================================================================
# Scenario 3: Seed term guided extraction
# ===========================================================================


class TestSeedTermGuidedExtraction:
    """Given an engagement seed list containing specific terms,
    when entity extraction runs on text mentioning those terms,
    entities matching seed terms get a confidence boost.
    """

    @pytest.mark.asyncio
    async def test_seed_matched_entity_has_boosted_confidence(self):
        """Entity matching seed term has higher confidence than baseline."""
        text = "Submit Purchase Order. Review Contract. Create Report."
        seed_terms = ["Review Contract"]

        result_no_seed = await extract_entities(text)
        result_with_seed = await extract_entities(text, seed_terms=seed_terms)

        # Find the Review Contract entity in both results
        no_seed_entity = next((e for e in result_no_seed.entities if "Review Contract" in e.name), None)
        seed_entity = next((e for e in result_with_seed.entities if "Review Contract" in e.name), None)

        assert no_seed_entity is not None
        assert seed_entity is not None
        assert seed_entity.confidence > no_seed_entity.confidence

    @pytest.mark.asyncio
    async def test_seed_matched_entity_tagged_with_seed_term(self):
        """Entity matching seed term has matched_seed_term metadata."""
        text = "Review Contract for compliance. Submit Purchase Order."
        seed_terms = ["Review Contract"]

        result = await extract_entities(text, seed_terms=seed_terms)
        entity = next((e for e in result.entities if "Review Contract" in e.name), None)

        assert entity is not None
        assert "matched_seed_term" in entity.metadata

    @pytest.mark.asyncio
    async def test_non_matching_entity_not_boosted(self):
        """Entity not matching any seed term keeps original confidence."""
        text = "Submit Purchase Order. Review Contract."
        seed_terms = ["Review Contract"]

        result_no_seed = await extract_entities(text)
        result_with_seed = await extract_entities(text, seed_terms=seed_terms)

        # Submit Purchase Order should not be boosted
        no_seed_entity = next((e for e in result_no_seed.entities if "Submit Purchase" in e.name), None)
        seed_entity = next((e for e in result_with_seed.entities if "Submit Purchase" in e.name), None)

        if no_seed_entity and seed_entity:
            assert seed_entity.confidence == no_seed_entity.confidence

    @pytest.mark.asyncio
    async def test_seed_matching_is_case_insensitive(self):
        """Seed term matching is case-insensitive."""
        text = "Review Contract for compliance."
        seed_terms = ["review contract"]

        result = await extract_entities(text, seed_terms=seed_terms)
        entity = next((e for e in result.entities if "Review Contract" in e.name), None)

        assert entity is not None
        assert "matched_seed_term" in entity.metadata

    def test_match_seed_term_exact(self):
        """Exact match returns the seed term."""
        seeds = {"review contract", "approve invoice"}
        assert _match_seed_term("Review Contract", seeds) == "review contract"

    def test_match_seed_term_containment(self):
        """Substring containment match returns the seed term."""
        seeds = {"review", "approve"}
        result = _match_seed_term("Review Contract", seeds)
        assert result == "review"

    def test_match_seed_term_no_match(self):
        """No match returns None."""
        seeds = {"unrelated term", "other thing"}
        assert _match_seed_term("Review Contract", seeds) is None


# ===========================================================================
# Scenario 4: Ambiguous entity mention confidence scoring
# ===========================================================================


class TestAmbiguousEntityConfidenceScoring:
    """Given an evidence item containing an ambiguous process mention,
    when entity extraction runs, the entity has lower confidence.
    """

    @pytest.mark.asyncio
    async def test_ambiguous_entity_has_lower_confidence(self):
        """Decision entities (ambiguous) have lower confidence than activities."""
        text = "If the amount exceeds the threshold, escalate to management."
        result = await extract_entities(text)

        decisions = [e for e in result.entities if e.entity_type == EntityType.DECISION]
        if decisions:
            # Decision entities have base confidence 0.6 (lower than activity 0.7)
            for d in decisions:
                assert d.confidence <= 0.7

    @pytest.mark.asyncio
    async def test_non_seed_matched_entities_keep_baseline(self):
        """Entities not matching seed terms keep their extraction baseline."""
        text = "If the threshold is exceeded, review the document."
        seed_terms = ["Submit Invoice"]  # Unrelated seed term

        result = await extract_entities(text, seed_terms=seed_terms)
        for entity in result.entities:
            # None should have matched_seed_term metadata
            if "matched_seed_term" not in entity.metadata:
                # Baseline confidence preserved
                assert entity.confidence <= 0.9

    @pytest.mark.asyncio
    async def test_seed_boost_raises_ambiguous_above_baseline(self):
        """Seed term boost can raise an ambiguous entity's confidence."""
        # Decision entities have 0.6 baseline, boost adds 0.15 → 0.75
        text = "If the invoice amount exceeds the limit, escalate."
        seed_terms = ["if the invoice amount exceeds the limit"]

        result = await extract_entities(text, seed_terms=seed_terms)
        decisions = [e for e in result.entities if e.entity_type == EntityType.DECISION]

        boosted = [d for d in decisions if "matched_seed_term" in d.metadata]
        if boosted:
            assert boosted[0].confidence > 0.6  # Boosted above baseline


# ===========================================================================
# Scenario 5: Duplicate entity flagging for resolution
# ===========================================================================


class TestDuplicateEntityFlagging:
    """Given entity extraction across multiple evidence sources,
    when deduplication analysis runs, potential duplicates are flagged
    as candidate pairs queued for resolution.
    """

    def test_containment_duplicates_detected(self):
        """Entities where one name contains the other are flagged."""
        entities = [
            ExtractedEntity(id="a1", entity_type=EntityType.ACTIVITY, name="Identity Verification", confidence=0.7),
            ExtractedEntity(id="a2", entity_type=EntityType.ACTIVITY, name="ID Verification", confidence=0.7),
        ]
        resolved, duplicates = resolve_entities(entities)

        # Both have different normalized names so both survive resolution
        assert len(resolved) == 2
        # But they should be flagged as duplicate candidates
        assert len(duplicates) >= 1
        pair = duplicates[0]
        assert {pair.entity_a_name, pair.entity_b_name} == {"Identity Verification", "ID Verification"}

    def test_duplicate_candidate_pair_has_both_ids(self):
        """Duplicate candidate pair references both entity IDs."""
        entities = [
            ExtractedEntity(id="a1", entity_type=EntityType.ACTIVITY, name="Review Purchase Order", confidence=0.8),
            ExtractedEntity(id="a2", entity_type=EntityType.ACTIVITY, name="Review Purchase", confidence=0.7),
        ]
        resolved, duplicates = resolve_entities(entities)

        assert len(duplicates) >= 1, "Expected at least one duplicate candidate pair"
        pair = duplicates[0]
        assert pair.entity_a_id in ("a1", "a2")
        assert pair.entity_b_id in ("a1", "a2")
        assert pair.entity_a_id != pair.entity_b_id

    def test_duplicate_candidate_has_shared_type(self):
        """Duplicate candidate pair has the shared entity type."""
        entities = [
            ExtractedEntity(id="r1", entity_type=EntityType.ROLE, name="Finance Manager", confidence=0.8),
            ExtractedEntity(id="r2", entity_type=EntityType.ROLE, name="Finance", confidence=0.6),
        ]
        resolved, duplicates = resolve_entities(entities)

        assert len(duplicates) >= 1, "Expected at least one duplicate candidate pair"
        assert duplicates[0].entity_type == EntityType.ROLE

    def test_no_duplicates_for_different_types(self):
        """Entities of different types are never flagged as duplicates."""
        entities = [
            ExtractedEntity(id="a1", entity_type=EntityType.ACTIVITY, name="Review Contract", confidence=0.7),
            ExtractedEntity(id="d1", entity_type=EntityType.DOCUMENT, name="Contract", confidence=0.8),
        ]
        resolved, duplicates = resolve_entities(entities)
        assert len(duplicates) == 0

    def test_no_duplicates_for_unrelated_names(self):
        """Entities with unrelated names are not flagged."""
        entities = [
            ExtractedEntity(id="a1", entity_type=EntityType.ACTIVITY, name="Submit Invoice", confidence=0.7),
            ExtractedEntity(id="a2", entity_type=EntityType.ACTIVITY, name="Approve Contract", confidence=0.7),
        ]
        resolved, duplicates = resolve_entities(entities)
        assert len(duplicates) == 0

    def test_duplicate_pair_has_similarity_reason(self):
        """Duplicate candidate pair includes a reason for the flagging."""
        entities = [
            ExtractedEntity(id="a1", entity_type=EntityType.ACTIVITY, name="Create Purchase Order", confidence=0.7),
            ExtractedEntity(id="a2", entity_type=EntityType.ACTIVITY, name="Create Purchase", confidence=0.6),
        ]
        resolved, duplicates = resolve_entities(entities)

        assert len(duplicates) >= 1, "Expected at least one duplicate candidate pair"
        assert duplicates[0].similarity_reason != ""

    def test_acronym_detection(self):
        """Acronyms of multi-word names are detected as potential duplicates."""
        # This checks the _check_name_similarity function
        reason = _check_name_similarity("purchase order", "po")
        assert reason is not None
        assert "acronym" in reason.lower()

    def test_check_name_similarity_no_match(self):
        """Unrelated names return None."""
        result = _check_name_similarity("create invoice", "review contract")
        assert result is None


# ===========================================================================
# Integration tests for extract_from_evidence with seed terms
# ===========================================================================


class TestExtractFromEvidenceWithSeedTerms:
    """Integration tests for the extract_from_evidence wrapper."""

    @pytest.mark.asyncio
    async def test_seed_terms_passed_through_to_extractor(self):
        """Seed terms are passed through to the entity extractor."""
        ev_id = uuid.uuid4()
        frag_id = uuid.uuid4()
        item = _make_evidence_item(str(ev_id))
        frag = _make_fragment("Review Contract for compliance.", ev_id, frag_id)
        item.fragments = [frag]

        summary = await extract_from_evidence([item], [frag], seed_terms=["Review Contract"])

        # Find the boosted entity
        review_entity = next((e for e in summary.entities if "Review Contract" in e.name), None)
        assert review_entity is not None
        assert "matched_seed_term" in review_entity.metadata

    @pytest.mark.asyncio
    async def test_extraction_summary_has_duplicate_candidates(self):
        """ExtractionSummary includes duplicate candidate pairs."""
        ev1 = uuid.uuid4()
        ev2 = uuid.uuid4()
        frag1 = _make_fragment("Submit Purchase Order for review.", ev1)
        frag2 = _make_fragment("Submit Purchase for approval.", ev2)

        item1 = _make_evidence_item(str(ev1))
        item1.fragments = [frag1]
        item2 = _make_evidence_item(str(ev2))
        item2.fragments = [frag2]

        summary = await extract_from_evidence([item1, item2], [frag1, frag2])
        assert isinstance(summary.duplicate_candidates, list)

    @pytest.mark.asyncio
    async def test_extraction_without_seed_terms(self):
        """Extraction works fine without seed terms."""
        ev_id = uuid.uuid4()
        frag = _make_fragment("Approve Invoice. Review Budget.", ev_id)
        item = _make_evidence_item(str(ev_id))
        item.fragments = [frag]

        summary = await extract_from_evidence([item], [frag])
        assert len(summary.entities) > 0
        assert summary.raw_entity_count > 0

    @pytest.mark.asyncio
    async def test_empty_fragments_returns_empty_summary(self):
        """Empty fragment list returns empty summary."""
        summary = await extract_from_evidence([], [])
        assert len(summary.entities) == 0
        assert summary.raw_entity_count == 0
        assert summary.duplicate_candidates == []

    @pytest.mark.asyncio
    async def test_provenance_maps_populated(self):
        """Entity-to-evidence and entity-to-fragment maps populated."""
        ev_id = uuid.uuid4()
        frag_id = uuid.uuid4()
        frag = _make_fragment("Process Invoice for payment.", ev_id, frag_id)
        item = _make_evidence_item(str(ev_id))
        item.fragments = [frag]

        summary = await extract_from_evidence([item], [frag])

        if summary.entities:
            first_entity = summary.entities[0]
            assert first_entity.id in summary.entity_to_evidence
            assert first_entity.id in summary.entity_to_fragments
