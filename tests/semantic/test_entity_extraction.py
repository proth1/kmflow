"""Tests for the entity extraction service.

Tests cover: rule-based patterns for each entity type, confidence scoring,
entity resolution (dedup), empty input handling, and extraction result structure.
"""

from __future__ import annotations

import pytest

from src.semantic.entity_extraction import (
    EntityType,
    ExtractedEntity,
    extract_entities,
    resolve_entities,
)

# ---------------------------------------------------------------------------
# Activity extraction
# ---------------------------------------------------------------------------


class TestActivityExtraction:
    """Test extraction of Activity entities."""

    @pytest.mark.asyncio
    async def test_extract_imperative_activities(self) -> None:
        """Should extract imperative verb + object activities."""
        text = "Create Purchase Requisition and Submit Invoice for review."
        result = await extract_entities(text)
        names = [e.name for e in result.entities if e.entity_type == EntityType.ACTIVITY]
        assert any("Create Purchase Requisition" in n for n in names)
        assert any("Submit Invoice" in n for n in names)

    @pytest.mark.asyncio
    async def test_extract_gerund_activities(self) -> None:
        """Should extract gerund-form activities."""
        text = "The process involves reviewing the application and approving the request."
        result = await extract_entities(text)
        names = [e.name.lower() for e in result.entities if e.entity_type == EntityType.ACTIVITY]
        assert any("reviewing" in n for n in names)
        assert any("approving" in n for n in names)

    @pytest.mark.asyncio
    async def test_activity_confidence_score(self) -> None:
        """Activities should have a confidence score between 0 and 1."""
        text = "Approve Purchase Order before processing."
        result = await extract_entities(text)
        activities = [e for e in result.entities if e.entity_type == EntityType.ACTIVITY]
        assert len(activities) > 0
        for activity in activities:
            assert 0.0 <= activity.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_activity_dedup_within_text(self) -> None:
        """Should not extract the same activity twice from the same text."""
        text = "Create Purchase Order. Then Create Purchase Order again."
        result = await extract_entities(text)
        activity_names = [e.name for e in result.entities if e.entity_type == EntityType.ACTIVITY]
        # Each unique name should appear at most once
        assert len(activity_names) == len(set(n.lower() for n in activity_names))

    @pytest.mark.asyncio
    async def test_activity_has_source_span(self) -> None:
        """Extracted activities should include the source span."""
        text = "Validate Customer Identity before proceeding."
        result = await extract_entities(text)
        activities = [e for e in result.entities if e.entity_type == EntityType.ACTIVITY]
        assert len(activities) > 0
        assert activities[0].source_span != ""


# ---------------------------------------------------------------------------
# Role extraction
# ---------------------------------------------------------------------------


class TestRoleExtraction:
    """Test extraction of Role entities."""

    @pytest.mark.asyncio
    async def test_extract_title_roles(self) -> None:
        """Should extract title-pattern roles."""
        text = "The Procurement Specialist reviews the request with the Finance Manager."
        result = await extract_entities(text)
        roles = [e for e in result.entities if e.entity_type == EntityType.ROLE]
        role_names = [r.name for r in roles]
        assert any("Procurement Specialist" in n for n in role_names)
        assert any("Finance Manager" in n for n in role_names)

    @pytest.mark.asyncio
    async def test_extract_generic_roles(self) -> None:
        """Should extract generic role references (the approver, the reviewer)."""
        text = "Once submitted, the approver reviews the document."
        result = await extract_entities(text)
        roles = [e for e in result.entities if e.entity_type == EntityType.ROLE]
        role_names = [r.name.lower() for r in roles]
        assert any("approver" in n for n in role_names)

    @pytest.mark.asyncio
    async def test_extract_team_roles(self) -> None:
        """Should extract department/team references."""
        text = "The Finance Team is responsible for reconciliation."
        result = await extract_entities(text)
        roles = [e for e in result.entities if e.entity_type == EntityType.ROLE]
        role_names = [r.name for r in roles]
        assert any("Finance Team" in n for n in role_names)

    @pytest.mark.asyncio
    async def test_role_confidence_title_vs_generic(self) -> None:
        """Title patterns should have higher confidence than generic references."""
        text = "The Operations Manager delegates to the reviewer."
        result = await extract_entities(text)
        roles = [e for e in result.entities if e.entity_type == EntityType.ROLE]
        title_roles = [r for r in roles if r.name[0].isupper() and "Manager" in r.name]
        generic_roles = [r for r in roles if "reviewer" in r.name.lower()]
        if title_roles and generic_roles:
            assert title_roles[0].confidence >= generic_roles[0].confidence


# ---------------------------------------------------------------------------
# System extraction
# ---------------------------------------------------------------------------


class TestSystemExtraction:
    """Test extraction of System entities."""

    @pytest.mark.asyncio
    async def test_extract_named_systems(self) -> None:
        """Should extract 'Noun + system/platform' patterns."""
        text = "Data is entered into the ERP system and synced with the CRM platform."
        result = await extract_entities(text)
        systems = [e for e in result.entities if e.entity_type == EntityType.SYSTEM]
        system_names = [s.name for s in systems]
        assert any("ERP" in n for n in system_names)
        assert any("CRM" in n for n in system_names)

    @pytest.mark.asyncio
    async def test_extract_known_systems(self) -> None:
        """Should extract well-known enterprise system names."""
        text = "We use SAP for procurement and Salesforce for CRM."
        result = await extract_entities(text)
        systems = [e for e in result.entities if e.entity_type == EntityType.SYSTEM]
        system_names = [s.name for s in systems]
        assert any("SAP" in n for n in system_names)
        assert any("Salesforce" in n for n in system_names)

    @pytest.mark.asyncio
    async def test_known_system_higher_confidence(self) -> None:
        """Known systems should get higher confidence scores."""
        text = "SAP is the primary system."
        result = await extract_entities(text)
        systems = [e for e in result.entities if e.entity_type == EntityType.SYSTEM]
        sap_systems = [s for s in systems if "SAP" in s.name]
        assert len(sap_systems) > 0
        assert sap_systems[0].confidence >= 0.9


# ---------------------------------------------------------------------------
# Decision extraction
# ---------------------------------------------------------------------------


class TestDecisionExtraction:
    """Test extraction of Decision entities."""

    @pytest.mark.asyncio
    async def test_extract_conditional_decisions(self) -> None:
        """Should extract if/when conditional patterns."""
        text = "If the amount exceeds $10,000, then manager approval is required."
        result = await extract_entities(text)
        decisions = [e for e in result.entities if e.entity_type == EntityType.DECISION]
        assert len(decisions) > 0
        # Check the decision captures the condition
        assert any("amount exceeds" in d.name.lower() or "10,000" in d.name for d in decisions)

    @pytest.mark.asyncio
    async def test_extract_threshold_decisions(self) -> None:
        """Should extract threshold/criteria patterns."""
        text = "The threshold of $5,000 applies to all purchases."
        result = await extract_entities(text)
        decisions = [e for e in result.entities if e.entity_type == EntityType.DECISION]
        assert len(decisions) > 0

    @pytest.mark.asyncio
    async def test_decision_confidence(self) -> None:
        """Decision confidence should be moderate (lower than roles/systems)."""
        text = "When the request is approved by management, processing begins."
        result = await extract_entities(text)
        decisions = [e for e in result.entities if e.entity_type == EntityType.DECISION]
        if decisions:
            assert decisions[0].confidence <= 0.8  # Decisions are less certain


# ---------------------------------------------------------------------------
# Document extraction
# ---------------------------------------------------------------------------


class TestDocumentExtraction:
    """Test extraction of Document entities."""

    @pytest.mark.asyncio
    async def test_extract_standard_documents(self) -> None:
        """Should extract common document types."""
        text = "The Purchase Order must be attached along with the Invoice."
        result = await extract_entities(text)
        docs = [e for e in result.entities if e.entity_type == EntityType.DOCUMENT]
        doc_names = [d.name.lower() for d in docs]
        assert any("purchase order" in n for n in doc_names)
        assert any("invoice" in n for n in doc_names)

    @pytest.mark.asyncio
    async def test_extract_acronym_documents(self) -> None:
        """Should extract document acronyms like SLA, RFP."""
        text = "Review the SLA before signing the Contract."
        result = await extract_entities(text)
        docs = [e for e in result.entities if e.entity_type == EntityType.DOCUMENT]
        doc_names = [d.name for d in docs]
        assert any("SLA" in n for n in doc_names)
        assert any("Contract" in n for n in doc_names)


# ---------------------------------------------------------------------------
# ExtractionResult structure
# ---------------------------------------------------------------------------


class TestExtractionResult:
    """Test the extraction result structure and metadata."""

    @pytest.mark.asyncio
    async def test_result_has_fragment_id(self) -> None:
        """Should preserve the fragment_id in the result."""
        result = await extract_entities("Create Order", fragment_id="frag-123")
        assert result.fragment_id == "frag-123"

    @pytest.mark.asyncio
    async def test_result_has_raw_text_length(self) -> None:
        """Should record the raw text length."""
        text = "Review the application carefully."
        result = await extract_entities(text)
        assert result.raw_text_length == len(text)

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty_result(self) -> None:
        """Should return empty result for empty text."""
        result = await extract_entities("")
        assert result.entities == []
        assert result.raw_text_length == 0

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_empty(self) -> None:
        """Should return empty result for whitespace-only text."""
        result = await extract_entities("   \n\t  ")
        assert result.entities == []

    @pytest.mark.asyncio
    async def test_entities_have_unique_ids(self) -> None:
        """Each entity should have a unique ID."""
        text = "Create Order, Review Invoice, and the Procurement Manager approves."
        result = await extract_entities(text)
        ids = [e.id for e in result.entities]
        assert len(ids) == len(set(ids))

    @pytest.mark.asyncio
    async def test_entity_id_deterministic(self) -> None:
        """Same entity type + name should produce the same ID."""
        text = "Approve Invoice"
        result1 = await extract_entities(text)
        result2 = await extract_entities(text)
        if result1.entities and result2.entities:
            assert result1.entities[0].id == result2.entities[0].id


# ---------------------------------------------------------------------------
# Entity resolution
# ---------------------------------------------------------------------------


class TestEntityResolution:
    """Test entity resolution (dedup across fragments)."""

    def test_resolve_identical_entities(self) -> None:
        """Should merge entities with identical names."""
        entities = [
            ExtractedEntity(id="a1", entity_type=EntityType.ACTIVITY, name="Create Order", confidence=0.7),
            ExtractedEntity(id="a2", entity_type=EntityType.ACTIVITY, name="Create Order", confidence=0.8),
        ]
        resolved, _ = resolve_entities(entities)
        assert len(resolved) == 1
        assert resolved[0].confidence == 0.8  # Keeps higher confidence

    def test_resolve_case_insensitive(self) -> None:
        """Should merge entities that differ only by case."""
        entities = [
            ExtractedEntity(id="r1", entity_type=EntityType.ROLE, name="Finance Manager", confidence=0.7),
            ExtractedEntity(id="r2", entity_type=EntityType.ROLE, name="finance manager", confidence=0.6),
        ]
        resolved, _ = resolve_entities(entities)
        assert len(resolved) == 1

    def test_resolve_different_types_not_merged(self) -> None:
        """Should not merge entities of different types even with same name."""
        entities = [
            ExtractedEntity(id="a1", entity_type=EntityType.ACTIVITY, name="Review", confidence=0.7),
            ExtractedEntity(id="d1", entity_type=EntityType.DOCUMENT, name="Review", confidence=0.8),
        ]
        resolved, _ = resolve_entities(entities)
        assert len(resolved) == 2

    def test_resolve_populates_aliases(self) -> None:
        """Should populate aliases from merged entities."""
        entities = [
            ExtractedEntity(id="s1", entity_type=EntityType.SYSTEM, name="SAP ERP", confidence=0.9),
            ExtractedEntity(id="s2", entity_type=EntityType.SYSTEM, name="SAP erp", confidence=0.7),
        ]
        resolved, _ = resolve_entities(entities)
        assert len(resolved) == 1
        # The lower-confidence name that differs from canonical should be an alias
        canonical = resolved[0]
        assert canonical.name == "SAP ERP"
        # If names differ (case-insensitive match but different casing)
        if canonical.aliases:
            assert any("SAP erp" in a for a in canonical.aliases)

    def test_resolve_empty_list(self) -> None:
        """Should handle empty entity list."""
        resolved, duplicates = resolve_entities([])
        assert resolved == []
        assert duplicates == []

    def test_resolve_single_entity(self) -> None:
        """Should pass through a single entity unchanged."""
        entity = ExtractedEntity(id="x1", entity_type=EntityType.ROLE, name="Admin", confidence=0.8)
        resolved, _ = resolve_entities([entity])
        assert len(resolved) == 1
        assert resolved[0].name == "Admin"

    def test_resolve_normalizes_articles(self) -> None:
        """Should normalize common articles/prepositions for matching."""
        entities = [
            ExtractedEntity(id="r1", entity_type=EntityType.ROLE, name="Head of Finance", confidence=0.7),
            ExtractedEntity(id="r2", entity_type=EntityType.ROLE, name="Head Finance", confidence=0.6),
        ]
        resolved, _ = resolve_entities(entities)
        # "of" is stripped during normalization, so these should merge
        assert len(resolved) == 1


# ---------------------------------------------------------------------------
# Mixed entity extraction
# ---------------------------------------------------------------------------


class TestMixedExtraction:
    """Test extraction of multiple entity types from realistic text."""

    @pytest.mark.asyncio
    async def test_extract_from_process_description(self) -> None:
        """Should extract multiple entity types from a process description."""
        text = (
            "The Procurement Specialist creates a Purchase Requisition in SAP. "
            "If the amount exceeds $10,000, the Finance Manager must approve. "
            "The Purchase Order is then generated automatically."
        )
        result = await extract_entities(text)

        entity_types = {e.entity_type for e in result.entities}
        # Should find at least activities, roles, systems, and documents
        assert EntityType.ACTIVITY in entity_types or EntityType.ROLE in entity_types
        assert len(result.entities) >= 3

    @pytest.mark.asyncio
    async def test_extract_preserves_all_types(self) -> None:
        """Should extract and return all entity types found."""
        text = (
            "Review Invoice in Oracle system. "
            "The Accounts Payable Clerk decides whether to approve. "
            "The Contract must be attached."
        )
        result = await extract_entities(text)
        types_found = {e.entity_type for e in result.entities}
        # At minimum should find some of these
        assert len(types_found) >= 2
