"""Tests for conformance API routes (src/api/routes/conformance.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

SAMPLE_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="Process_1" isExecutable="true">
    <bpmn:startEvent id="Start" name="Start"/>
    <bpmn:task id="Task_1" name="Review"/>
    <bpmn:endEvent id="End" name="End"/>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="Start" targetRef="Task_1"/>
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_1" targetRef="End"/>
  </bpmn:process>
</bpmn:definitions>"""


@pytest.mark.asyncio
class TestConformanceRoutes:
    async def test_create_reference_model(self, client, mock_db_session):
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        response = await client.post(
            "/api/v1/conformance/reference-models",
            json={
                "name": "Standard Loan Origination",
                "industry": "financial_services",
                "process_area": "lending",
                "bpmn_xml": SAMPLE_BPMN,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Standard Loan Origination"
        assert data["industry"] == "financial_services"

    async def test_create_reference_model_invalid_bpmn(self, client, mock_db_session):
        response = await client.post(
            "/api/v1/conformance/reference-models",
            json={
                "name": "Bad Model",
                "industry": "finance",
                "process_area": "lending",
                "bpmn_xml": "<invalid/>",
            },
        )
        assert response.status_code == 400

    async def test_create_reference_model_missing_fields(self, client, mock_db_session):
        response = await client.post(
            "/api/v1/conformance/reference-models",
            json={"name": "Incomplete"},
        )
        assert response.status_code == 422

    async def test_list_reference_models(self, client, mock_db_session):
        m = MagicMock()
        m.id = uuid4()
        m.name = "Model 1"
        m.industry = "finance"
        m.process_area = "lending"
        m.created_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [m]
        mock_db_session.execute.return_value = mock_result

        response = await client.get("/api/v1/conformance/reference-models")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Model 1"

    async def test_list_reference_models_empty(self, client, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = await client.get("/api/v1/conformance/reference-models")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    async def test_conformance_check_ref_not_found(self, client, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.post(
            "/api/v1/conformance/check",
            json={
                "engagement_id": str(uuid4()),
                "reference_model_id": str(uuid4()),
                "observed_bpmn_xml": SAMPLE_BPMN,
            },
        )
        assert response.status_code == 404

    async def test_conformance_check_with_xml(self, client, mock_db_session):
        ref_model = MagicMock()
        ref_model.id = uuid4()
        ref_model.bpmn_xml = SAMPLE_BPMN

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ref_model
        mock_db_session.execute.return_value = mock_result
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        response = await client.post(
            "/api/v1/conformance/check",
            json={
                "engagement_id": str(uuid4()),
                "reference_model_id": str(ref_model.id),
                "observed_bpmn_xml": SAMPLE_BPMN,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "fitness_score" in data
        assert "precision_score" in data
        assert "deviations" in data
        assert data["fitness_score"] == 1.0

    async def test_list_conformance_results(self, client, mock_db_session):
        cr = MagicMock()
        cr.id = uuid4()
        cr.engagement_id = uuid4()
        cr.reference_model_id = uuid4()
        cr.fitness_score = 0.85
        cr.precision_score = 0.9
        cr.deviations = {"items": []}
        cr.created_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [cr]
        mock_db_session.execute.return_value = mock_result

        response = await client.get("/api/v1/conformance/results")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["fitness_score"] == 0.85
