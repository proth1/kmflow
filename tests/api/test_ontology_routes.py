"""Tests for ontology API routes (KMFLOW-6)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.routes.ontology import (
    derive_ontology,
    export_ontology,
    get_ontology,
    validate_ontology,
)
from src.core.models.ontology import OntologyStatus, OntologyVersion


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _mock_request(neo4j_driver: AsyncMock | None = AsyncMock()) -> MagicMock:
    request = MagicMock()
    request.app.state.neo4j_driver = neo4j_driver
    return request


def _mock_ontology(engagement_id: uuid.UUID) -> MagicMock:
    ontology = MagicMock(spec=OntologyVersion)
    ontology.id = uuid.uuid4()
    ontology.engagement_id = engagement_id
    ontology.version = 1
    ontology.status = OntologyStatus.DERIVED
    ontology.completeness_score = 0.8
    ontology.derived_at = MagicMock()
    ontology.derived_at.isoformat.return_value = "2026-03-11T00:00:00+00:00"
    return ontology


class TestDeriveOntology:
    @pytest.mark.asyncio
    async def test_triggers_derivation(self) -> None:
        eng_id = uuid.uuid4()
        session = AsyncMock()
        request = _mock_request()

        expected = {
            "ontology_id": str(uuid.uuid4()),
            "version": 1,
            "status": "derived",
            "class_count": 3,
            "property_count": 5,
            "axiom_count": 2,
            "completeness_score": 0.85,
        }

        with patch("src.api.routes.ontology.OntologyDerivationService") as mock_cls:
            mock_service = AsyncMock()
            mock_service.derive = AsyncMock(return_value=expected)
            mock_cls.return_value = mock_service

            result = await derive_ontology(eng_id, request, session, _mock_user(), None)

        assert result["class_count"] == 3
        assert result["completeness_score"] == 0.85

    @pytest.mark.asyncio
    async def test_503_when_neo4j_unavailable(self) -> None:
        eng_id = uuid.uuid4()
        session = AsyncMock()
        request = _mock_request(neo4j_driver=None)

        with pytest.raises(Exception) as exc_info:
            await derive_ontology(eng_id, request, session, _mock_user(), None)

        assert exc_info.value.status_code == 503


class TestGetOntology:
    @pytest.mark.asyncio
    async def test_returns_latest_ontology(self) -> None:
        eng_id = uuid.uuid4()
        session = AsyncMock()

        ontology = _mock_ontology(eng_id)

        # First execute returns ontology
        ont_result = MagicMock()
        ont_result.scalar_one_or_none.return_value = ontology

        # Next three return classes, properties, axioms
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[ont_result, empty_result, empty_result, empty_result])

        result = await get_ontology(eng_id, session, _mock_user(), None)

        assert result["version"] == 1
        assert result["status"] == "derived"
        assert result["classes"] == []
        assert result["properties"] == []
        assert result["axioms"] == []

    @pytest.mark.asyncio
    async def test_404_when_no_ontology(self) -> None:
        eng_id = uuid.uuid4()
        session = AsyncMock()

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        with pytest.raises(Exception) as exc_info:
            await get_ontology(eng_id, session, _mock_user(), None)

        assert exc_info.value.status_code == 404


class TestExportOntology:
    @pytest.mark.asyncio
    async def test_exports_yaml(self) -> None:
        eng_id = uuid.uuid4()
        session = AsyncMock()

        ontology = _mock_ontology(eng_id)
        ont_result = MagicMock()
        ont_result.scalar_one_or_none.return_value = ontology
        session.execute = AsyncMock(return_value=ont_result)

        expected = {
            "content": "ontology:\n  version: 1\n",
            "content_hash": "abc123",
            "format": "yaml",
            "ontology_id": str(ontology.id),
            "version": 1,
        }

        with patch("src.api.routes.ontology.OntologyExportService") as mock_cls:
            mock_service = AsyncMock()
            mock_service.export = AsyncMock(return_value=expected)
            mock_cls.return_value = mock_service

            result = await export_ontology(eng_id, "yaml", session, _mock_user(), None)

        assert result["format"] == "yaml"
        assert "content" in result

    @pytest.mark.asyncio
    async def test_404_when_no_ontology(self) -> None:
        eng_id = uuid.uuid4()
        session = AsyncMock()

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        with pytest.raises(Exception) as exc_info:
            await export_ontology(eng_id, "yaml", session, _mock_user(), None)

        assert exc_info.value.status_code == 404


class TestValidateOntology:
    @pytest.mark.asyncio
    async def test_runs_validation(self) -> None:
        eng_id = uuid.uuid4()
        session = AsyncMock()

        ontology = _mock_ontology(eng_id)
        ont_result = MagicMock()
        ont_result.scalar_one_or_none.return_value = ontology
        session.execute = AsyncMock(return_value=ont_result)

        expected = {
            "ontology_id": str(ontology.id),
            "completeness_score": 0.8,
            "orphan_classes": [],
            "recommendations": [],
        }

        with patch("src.api.routes.ontology.OntologyValidationService") as mock_cls:
            mock_service = AsyncMock()
            mock_service.validate = AsyncMock(return_value=expected)
            mock_cls.return_value = mock_service

            result = await validate_ontology(eng_id, session, _mock_user(), None)

        assert result["completeness_score"] == 0.8

    @pytest.mark.asyncio
    async def test_404_when_no_ontology(self) -> None:
        eng_id = uuid.uuid4()
        session = AsyncMock()

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        with pytest.raises(Exception) as exc_info:
            await validate_ontology(eng_id, session, _mock_user(), None)

        assert exc_info.value.status_code == 404
