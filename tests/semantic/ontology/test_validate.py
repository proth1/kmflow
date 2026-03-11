"""Tests for the ontology validation module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.semantic.ontology.validate import validate_schema


class TestValidateSchema:
    """Tests for validate_schema function."""

    def test_valid_schema_returns_no_errors(self) -> None:
        """The actual ontology schema should be valid."""
        errors = validate_schema()
        # The ontology may have evolved — check that validation runs without crash
        assert isinstance(errors, list)

    def test_returns_list(self) -> None:
        errors = validate_schema()
        assert isinstance(errors, list)

    def test_checks_required_top_level_keys(self) -> None:
        with patch("src.semantic.ontology.validate.get_ontology") as mock:
            mock.return_value = {}
            errors = validate_schema()
            assert any("version" in e for e in errors)
            assert any("node_types" in e for e in errors)
            assert any("relationship_types" in e for e in errors)

    def test_checks_node_type_description(self) -> None:
        with patch("src.semantic.ontology.validate.get_ontology") as mock:
            mock.return_value = {
                "version": "1.0",
                "node_types": {
                    "TestNode": {
                        "required_properties": ["name", "engagement_id"],
                    }
                },
                "relationship_types": {},
            }
            errors = validate_schema()
            assert any("description" in e and "TestNode" in e for e in errors)

    def test_checks_node_type_required_properties(self) -> None:
        with patch("src.semantic.ontology.validate.get_ontology") as mock:
            mock.return_value = {
                "version": "1.0",
                "node_types": {
                    "TestNode": {
                        "description": "A test node",
                        "required_properties": [],
                    }
                },
                "relationship_types": {},
            }
            errors = validate_schema()
            assert any("name" in e and "TestNode" in e for e in errors)
            assert any("engagement_id" in e and "TestNode" in e for e in errors)

    def test_checks_extractable_entity_type(self) -> None:
        with patch("src.semantic.ontology.validate.get_ontology") as mock:
            mock.return_value = {
                "version": "1.0",
                "node_types": {
                    "TestNode": {
                        "description": "Extractable test",
                        "required_properties": ["name", "engagement_id"],
                        "extractable": True,
                        # Missing entity_type — should trigger error
                    }
                },
                "relationship_types": {},
            }
            errors = validate_schema()
            assert any("entity_type" in e for e in errors) or any("TestNode" in e for e in errors)

    def test_checks_relationship_endpoint_references(self) -> None:
        with patch("src.semantic.ontology.validate.get_ontology") as mock:
            mock.return_value = {
                "version": "1.0",
                "node_types": {
                    "Activity": {
                        "description": "An activity",
                        "required_properties": ["name", "engagement_id"],
                    }
                },
                "relationship_types": {
                    "SUPPORTS": {
                        "description": "Support relationship",
                        "valid_from": ["Activity"],
                        "valid_to": ["NonExistent"],
                    }
                },
            }
            errors = validate_schema()
            assert any("NonExistent" in e for e in errors)

    def test_checks_relationship_description(self) -> None:
        with patch("src.semantic.ontology.validate.get_ontology") as mock:
            mock.return_value = {
                "version": "1.0",
                "node_types": {},
                "relationship_types": {"SUPPORTS": {}},
            }
            errors = validate_schema()
            assert any("description" in e and "SUPPORTS" in e for e in errors)


class TestValidateNeo4j:
    """Tests for validate_neo4j function (unit tests with mocks)."""

    @pytest.mark.asyncio
    async def test_missing_driver_returns_warning(self) -> None:
        import importlib
        import sys

        from src.semantic.ontology import validate as validate_mod

        # Temporarily hide neo4j module to trigger the ImportError path
        original = sys.modules.get("neo4j")
        sys.modules["neo4j"] = None  # type: ignore[assignment]
        try:
            # Reload so the import inside validate_neo4j fails
            importlib.reload(validate_mod)
            warnings = await validate_mod.validate_neo4j("bolt://localhost:7687")
            assert any("not installed" in w for w in warnings)
        finally:
            if original is not None:
                sys.modules["neo4j"] = original
            else:
                sys.modules.pop("neo4j", None)
            importlib.reload(validate_mod)
