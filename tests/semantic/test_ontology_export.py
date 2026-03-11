"""Tests for ontology export service (KMFLOW-6)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.ontology import OntologyAxiom, OntologyClass, OntologyProperty, OntologyStatus, OntologyVersion
from src.semantic.ontology_export import OntologyExportService


def _make_ontology(engagement_id: uuid.UUID | None = None) -> MagicMock:
    ontology = MagicMock(spec=OntologyVersion)
    ontology.id = uuid.uuid4()
    ontology.engagement_id = engagement_id or uuid.uuid4()
    ontology.version = 1
    ontology.status = OntologyStatus.DERIVED
    ontology.completeness_score = 0.75
    ontology.derived_at = MagicMock()
    ontology.derived_at.isoformat.return_value = "2026-03-11T00:00:00+00:00"
    return ontology


def _make_class(ontology_id: uuid.UUID, name: str, parent_id: uuid.UUID | None = None) -> MagicMock:
    cls = MagicMock(spec=OntologyClass)
    cls.id = uuid.uuid4()
    cls.ontology_id = ontology_id
    cls.name = name
    cls.description = f"Class: {name}"
    cls.parent_class_id = parent_id
    cls.source_seed_terms = {"terms": [{"term": name.lower(), "domain": "general"}], "count": 1}
    cls.instance_count = 5
    cls.confidence = 0.8
    return cls


def _make_property(
    ontology_id: uuid.UUID,
    name: str,
    edge_type: str,
    domain_id: uuid.UUID | None = None,
    range_id: uuid.UUID | None = None,
) -> MagicMock:
    prop = MagicMock(spec=OntologyProperty)
    prop.id = uuid.uuid4()
    prop.ontology_id = ontology_id
    prop.name = name
    prop.source_edge_type = edge_type
    prop.domain_class_id = domain_id
    prop.range_class_id = range_id
    prop.usage_count = 10
    prop.confidence = 0.9
    return prop


def _make_axiom(ontology_id: uuid.UUID, expression: str) -> MagicMock:
    axiom = MagicMock(spec=OntologyAxiom)
    axiom.id = uuid.uuid4()
    axiom.ontology_id = ontology_id
    axiom.expression = expression
    axiom.axiom_type = "existential"
    axiom.confidence = 0.85
    axiom.source_pattern = {"frequency": 20}
    return axiom


class TestYamlExport:
    @pytest.mark.asyncio
    async def test_generates_valid_yaml(self) -> None:
        session = AsyncMock()
        ontology = _make_ontology()
        session.get = AsyncMock(return_value=ontology)

        cls1 = _make_class(ontology.id, "Activity")
        cls2 = _make_class(ontology.id, "Role")
        prop1 = _make_property(ontology.id, "performed by", "PERFORMED_BY", cls1.id, cls2.id)
        axiom1 = _make_axiom(ontology.id, "Every Activity performed by at least one Role")

        classes_result = MagicMock()
        classes_result.scalars.return_value.all.return_value = [cls1, cls2]
        props_result = MagicMock()
        props_result.scalars.return_value.all.return_value = [prop1]
        axioms_result = MagicMock()
        axioms_result.scalars.return_value.all.return_value = [axiom1]

        session.execute = AsyncMock(side_effect=[classes_result, props_result, axioms_result])
        session.commit = AsyncMock()

        service = OntologyExportService(session)
        result = await service.export(ontology.id, fmt="yaml")

        assert "content" in result
        assert "content_hash" in result
        assert result["format"] == "yaml"
        assert len(result["content_hash"]) == 64  # SHA-256 hex
        assert "Activity" in result["content"]
        assert "PERFORMED_BY" in result["content"]

    @pytest.mark.asyncio
    async def test_includes_version_metadata(self) -> None:
        session = AsyncMock()
        ontology = _make_ontology()
        session.get = AsyncMock(return_value=ontology)

        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)
        session.commit = AsyncMock()

        service = OntologyExportService(session)
        result = await service.export(ontology.id, fmt="yaml")

        assert "version: 1" in result["content"]
        assert "completeness_score" in result["content"]


class TestOwlExport:
    @pytest.mark.asyncio
    async def test_generates_owl_xml(self) -> None:
        session = AsyncMock()
        ontology = _make_ontology()
        session.get = AsyncMock(return_value=ontology)

        cls1 = _make_class(ontology.id, "Activity")
        prop1 = _make_property(ontology.id, "performed by", "PERFORMED_BY", cls1.id, None)
        axiom1 = _make_axiom(ontology.id, "Activity always has performer")

        classes_result = MagicMock()
        classes_result.scalars.return_value.all.return_value = [cls1]
        props_result = MagicMock()
        props_result.scalars.return_value.all.return_value = [prop1]
        axioms_result = MagicMock()
        axioms_result.scalars.return_value.all.return_value = [axiom1]

        session.execute = AsyncMock(side_effect=[classes_result, props_result, axioms_result])
        session.commit = AsyncMock()

        service = OntologyExportService(session)
        result = await service.export(ontology.id, fmt="owl")

        assert result["format"] == "owl"
        assert '<?xml version="1.0"' in result["content"]
        assert "owl#" in result["content"]
        assert "Activity" in result["content"]

    @pytest.mark.asyncio
    async def test_includes_subclass_axioms(self) -> None:
        session = AsyncMock()
        ontology = _make_ontology()
        session.get = AsyncMock(return_value=ontology)

        parent = _make_class(ontology.id, "Process")
        child = _make_class(ontology.id, "SubProcess", parent_id=parent.id)

        classes_result = MagicMock()
        classes_result.scalars.return_value.all.return_value = [parent, child]
        props_result = MagicMock()
        props_result.scalars.return_value.all.return_value = []
        axioms_result = MagicMock()
        axioms_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[classes_result, props_result, axioms_result])
        session.commit = AsyncMock()

        service = OntologyExportService(session)
        result = await service.export(ontology.id, fmt="owl")

        assert "SubClassOf" in result["content"]


class TestExportNotFound:
    @pytest.mark.asyncio
    async def test_raises_for_missing_ontology(self) -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)

        service = OntologyExportService(session)
        with pytest.raises(ValueError, match="not found"):
            await service.export(uuid.uuid4())
