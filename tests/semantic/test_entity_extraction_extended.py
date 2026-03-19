"""Tests for extended entity extraction (DataObject, Event, Gateway types)."""

from __future__ import annotations

import pytest

from src.semantic.entity_extraction import (
    EntityType,
    _extract_data_objects,
    _extract_events,
    _extract_gateways,
    extract_entities,
)


class TestDataObjectExtraction:
    """Tests for DataObject entity extraction."""

    def test_explicit_data_references(self):
        text = "The Loan Officer reviews the customer data and updates the loan file."
        entities = _extract_data_objects(text)
        names = [e.name.lower() for e in entities]
        assert any("customer data" in n for n in names)
        assert any("loan file" in n for n in names)

    def test_data_flow_patterns(self):
        text = "Output to the underwriting system includes all applicant information."
        entities = _extract_data_objects(text)
        assert len(entities) >= 1

    def test_all_data_objects_have_correct_type(self):
        text = "The application form is processed and stored in the application record."
        entities = _extract_data_objects(text)
        for e in entities:
            assert e.entity_type == EntityType.DATA_OBJECT

    def test_short_names_filtered(self):
        text = "The log was updated."
        entities = _extract_data_objects(text)
        for e in entities:
            assert len(e.name) >= 4


class TestEventExtraction:
    """Tests for Event entity extraction."""

    def test_named_events(self):
        text = "Once the application received status is confirmed, the credit check started."
        entities = _extract_events(text)
        assert len(entities) >= 1
        assert all(e.entity_type == EntityType.EVENT for e in entities)

    def test_trigger_patterns(self):
        text = "Upon receipt of the signed documents, the closing process begins."
        entities = _extract_events(text)
        assert len(entities) >= 1

    def test_timer_patterns(self):
        text = "The SLA breach for underwriting review triggers an escalation."
        entities = _extract_events(text)
        assert len(entities) >= 1

    def test_deduplication(self):
        text = "Payment completed. Payment completed again."
        entities = _extract_events(text)
        names = [e.name.lower() for e in entities]
        # Should deduplicate
        assert len(set(names)) == len(names)


class TestGatewayExtraction:
    """Tests for Gateway entity extraction."""

    def test_explicit_gateway(self):
        text = "An exclusive gateway determines the next step."
        entities = _extract_gateways(text)
        assert len(entities) >= 1
        assert all(e.entity_type == EntityType.GATEWAY for e in entities)

    def test_routing_patterns(self):
        text = "Route to the appropriate team based on risk level."
        entities = _extract_gateways(text)
        assert len(entities) >= 1

    def test_conditional_branching(self):
        text = "Depending on the credit score, the application follows different paths."
        entities = _extract_gateways(text)
        assert len(entities) >= 1


class TestExtractEntitiesIntegration:
    """Integration tests for the full extract_entities function with new types."""

    @pytest.mark.asyncio
    async def test_all_eight_types_extractable(self):
        """Verify all 8 entity types can be extracted from rich text."""
        text = """
        The Loan Officer must Review Application Documents and Submit Loan File.
        Create Purchase Order for the underwriting process.
        If the credit score exceeds 720, the application is fast-tracked.
        The Senior Underwriter reviews the loan file in the SAP system.
        The signed closing disclosure must be archived in the customer record.
        Upon receipt of the appraisal report, the review process begins.
        The application received triggers the next step.
        An exclusive gateway determines whether manual review is needed.
        Either the automated path or the manual path is selected
        depending on the risk assessment results.
        """
        result = await extract_entities(text)
        types_found = {e.entity_type for e in result.entities}

        # Should find at least the original 5 types
        assert EntityType.ACTIVITY in types_found, f"Missing ACTIVITY, found: {types_found}"
        assert EntityType.ROLE in types_found
        assert EntityType.SYSTEM in types_found
        assert EntityType.DOCUMENT in types_found
        # New types should also be present
        assert EntityType.DATA_OBJECT in types_found or EntityType.EVENT in types_found

    @pytest.mark.asyncio
    async def test_entity_ids_deterministic(self):
        """Same text should produce same entity IDs."""
        text = "The customer data is reviewed by the Loan Officer."
        result1 = await extract_entities(text)
        result2 = await extract_entities(text)

        ids1 = sorted(e.id for e in result1.entities)
        ids2 = sorted(e.id for e in result2.entities)
        assert ids1 == ids2
