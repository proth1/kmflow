"""Tests for POV API endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import (
    CorroborationLevel,
    GapSeverity,
    GapType,
    ProcessElementType,
    ProcessModelStatus,
)


@pytest.fixture
def mock_process_model():
    """Create a mock process model."""
    model = MagicMock()
    model.id = uuid.uuid4()
    model.engagement_id = uuid.uuid4()
    model.version = 1
    model.scope = "all"
    model.status = ProcessModelStatus.COMPLETED
    model.confidence_score = 0.75
    model.bpmn_xml = "<bpmn>test</bpmn>"
    model.element_count = 5
    model.evidence_count = 3
    model.contradiction_count = 1
    model.metadata_json = {"overall_confidence_level": "HIGH"}
    model.generated_at = None
    model.generated_by = "consensus_algorithm"
    return model


@pytest.fixture
def mock_process_element():
    """Create a mock process element."""
    elem = MagicMock()
    elem.id = uuid.uuid4()
    elem.model_id = uuid.uuid4()
    elem.element_type = ProcessElementType.ACTIVITY
    elem.name = "Submit Request"
    elem.confidence_score = 0.8
    elem.triangulation_score = 0.6
    elem.corroboration_level = CorroborationLevel.MODERATELY
    elem.evidence_count = 2
    elem.evidence_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    elem.metadata_json = {"confidence_level": "HIGH"}
    return elem


@pytest.fixture
def mock_contradiction():
    """Create a mock contradiction."""
    c = MagicMock()
    c.id = uuid.uuid4()
    c.model_id = uuid.uuid4()
    c.element_name = "Process Invoice"
    c.field_name = "quality_divergence"
    c.values = [{"evidence_id": "a", "quality_score": "0.95"}]
    c.resolution_value = "Use source A"
    c.resolution_reason = "Higher quality"
    c.evidence_ids = [str(uuid.uuid4())]
    return c


@pytest.fixture
def mock_gap():
    """Create a mock evidence gap."""
    g = MagicMock()
    g.id = uuid.uuid4()
    g.model_id = uuid.uuid4()
    g.gap_type = GapType.SINGLE_SOURCE
    g.description = "Task X has only one source"
    g.severity = GapSeverity.MEDIUM
    g.recommendation = "Collect more evidence"
    g.related_element_id = None
    return g


class TestTriggerPovGeneration:
    """Tests for POST /api/v1/pov/generate."""

    @pytest.mark.asyncio
    async def test_generate_returns_202(self, client, mock_db_session):
        """Generate endpoint returns 202 with job_id."""
        eng_id = str(uuid.uuid4())

        with patch("src.api.routes.pov.generate_pov") as mock_gen:
            model = MagicMock()
            model.id = uuid.uuid4()
            mock_gen.return_value = MagicMock(
                success=True,
                process_model=model,
                stats={"elements": 5},
                error="",
            )

            response = await client.post(
                "/api/v1/pov/generate",
                json={"engagement_id": eng_id, "scope": "all"},
            )

        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_generate_failed(self, client, mock_db_session):
        """Generate returns failed status when generation fails."""
        eng_id = str(uuid.uuid4())

        with patch("src.api.routes.pov.generate_pov") as mock_gen:
            model = MagicMock()
            model.id = uuid.uuid4()
            mock_gen.return_value = MagicMock(
                success=False,
                process_model=model,
                stats={},
                error="No evidence found",
            )

            response = await client.post(
                "/api/v1/pov/generate",
                json={"engagement_id": eng_id},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "failed"


class TestGetProcessModel:
    """Tests for GET /api/v1/pov/{model_id}."""

    @pytest.mark.asyncio
    async def test_get_model_found(self, client, mock_db_session, mock_process_model):
        """Returns process model when found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_process_model
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.get(f"/api/v1/pov/{mock_process_model.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(mock_process_model.id)
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_model_not_found(self, client, mock_db_session):
        """Returns 404 when model not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        model_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/pov/{model_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_model_invalid_id(self, client, mock_db_session):
        """Returns 400 for invalid model ID format."""
        response = await client.get("/api/v1/pov/not-a-uuid")

        assert response.status_code == 400


class TestGetProcessElements:
    """Tests for GET /api/v1/pov/{model_id}/elements."""

    @pytest.mark.asyncio
    async def test_get_elements_found(self, client, mock_db_session, mock_process_element):
        """Returns paginated elements when found."""
        model_id = uuid.uuid4()

        # First call: check model exists, Second call: get elements, Third call: count
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Model exists check
                result.scalar_one_or_none.return_value = model_id
            elif call_count == 2:
                # Elements query
                result.scalars.return_value.all.return_value = [mock_process_element]
            else:
                # Count query
                result.scalar.return_value = 1
            return result

        mock_db_session.execute = AsyncMock(side_effect=side_effect)

        response = await client.get(f"/api/v1/pov/{model_id}/elements")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_elements_model_not_found(self, client, mock_db_session):
        """Returns 404 when model not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        model_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/pov/{model_id}/elements")

        assert response.status_code == 404


class TestGetEvidenceMap:
    """Tests for GET /api/v1/pov/{model_id}/evidence-map."""

    @pytest.mark.asyncio
    async def test_evidence_map(self, client, mock_db_session, mock_process_element):
        """Returns evidence-to-element mappings."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_process_element]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        model_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/pov/{model_id}/evidence-map")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            assert "evidence_id" in data[0]
            assert "element_names" in data[0]

    @pytest.mark.asyncio
    async def test_evidence_map_empty(self, client, mock_db_session):
        """Returns 404 when no elements found."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        model_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/pov/{model_id}/evidence-map")

        assert response.status_code == 404


class TestGetEvidenceGaps:
    """Tests for GET /api/v1/pov/{model_id}/gaps."""

    @pytest.mark.asyncio
    async def test_get_gaps(self, client, mock_db_session, mock_gap):
        """Returns evidence gaps."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_gap]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        model_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/pov/{model_id}/gaps")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["gap_type"] == "single_source"


class TestGetContradictions:
    """Tests for GET /api/v1/pov/{model_id}/contradictions."""

    @pytest.mark.asyncio
    async def test_get_contradictions(self, client, mock_db_session, mock_contradiction):
        """Returns contradictions."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_contradiction]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        model_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/pov/{model_id}/contradictions")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["element_name"] == "Process Invoice"


class TestGetBPMNXml:
    """Tests for GET /api/v1/pov/{model_id}/bpmn."""

    @pytest.mark.asyncio
    async def test_get_bpmn_found(self, client, mock_db_session, mock_process_model, mock_process_element):
        """Returns BPMN XML and element confidences when model exists."""
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Model lookup
                result.scalar_one_or_none.return_value = mock_process_model
            elif call_count == 2:
                # Elements lookup
                result.scalars.return_value.all.return_value = [mock_process_element]
            return result

        mock_db_session.execute = AsyncMock(side_effect=side_effect)

        response = await client.get(f"/api/v1/pov/{mock_process_model.id}/bpmn")

        assert response.status_code == 200
        data = response.json()
        assert data["model_id"] == str(mock_process_model.id)
        assert data["bpmn_xml"] == "<bpmn>test</bpmn>"
        assert "Submit Request" in data["element_confidences"]
        assert data["element_confidences"]["Submit Request"] == 0.8

    @pytest.mark.asyncio
    async def test_get_bpmn_not_found(self, client, mock_db_session):
        """Returns 404 when model not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        model_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/pov/{model_id}/bpmn")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_bpmn_no_xml(self, client, mock_db_session, mock_process_model):
        """Returns 404 when model has no BPMN XML."""
        mock_process_model.bpmn_xml = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_process_model
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.get(f"/api/v1/pov/{mock_process_model.id}/bpmn")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_bpmn_invalid_id(self, client, mock_db_session):
        """Returns 400 for invalid model ID format."""
        response = await client.get("/api/v1/pov/not-a-uuid/bpmn")

        assert response.status_code == 400


class TestGetJobStatus:
    """Tests for GET /api/v1/pov/job/{job_id}."""

    @pytest.mark.asyncio
    async def test_job_not_found(self, client):
        """Returns 404 for unknown job."""
        response = await client.get(f"/api/v1/pov/job/{uuid.uuid4().hex}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_job_found_after_generation(self, client, mock_db_session, mock_redis_client):
        """Returns job status after generation is triggered."""
        eng_id = str(uuid.uuid4())

        # Make mock Redis actually persist values between setex/get
        redis_store: dict[str, str] = {}

        async def _setex(key, ttl, value):
            redis_store[key] = value

        async def _get(key):
            return redis_store.get(key)

        mock_redis_client.setex = AsyncMock(side_effect=_setex)
        mock_redis_client.get = AsyncMock(side_effect=_get)

        with patch("src.api.routes.pov.generate_pov") as mock_gen:
            model = MagicMock()
            model.id = uuid.uuid4()
            mock_gen.return_value = MagicMock(
                success=True,
                process_model=model,
                stats={"elements": 3},
                error="",
            )

            gen_response = await client.post(
                "/api/v1/pov/generate",
                json={"engagement_id": eng_id},
            )

        job_id = gen_response.json()["job_id"]
        response = await client.get(f"/api/v1/pov/job/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "completed"
