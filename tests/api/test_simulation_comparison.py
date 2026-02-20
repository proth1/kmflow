"""Tests for simulation comparison, coverage, and modifications API endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.models import (
    ModificationType,
    ScenarioModification,
    SimulationResult,
    SimulationScenario,
    SimulationStatus,
    SimulationType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scenario(**overrides) -> MagicMock:
    mock = MagicMock(spec=SimulationScenario)
    mock.id = overrides.get("id", uuid.uuid4())
    mock.engagement_id = overrides.get("engagement_id", uuid.uuid4())
    mock.process_model_id = overrides.get("process_model_id")
    mock.name = overrides.get("name", "Baseline")
    mock.simulation_type = overrides.get("simulation_type", SimulationType.WHAT_IF)
    mock.parameters = overrides.get("parameters")
    mock.description = overrides.get("description")
    mock.status = overrides.get("status", "draft")
    mock.evidence_confidence_score = overrides.get("evidence_confidence_score")
    mock.created_at = overrides.get("created_at", datetime.now(UTC))
    mock.modifications = overrides.get("modifications", [])
    return mock


def _make_result(**overrides) -> MagicMock:
    mock = MagicMock(spec=SimulationResult)
    mock.id = overrides.get("id", uuid.uuid4())
    mock.scenario_id = overrides.get("scenario_id", uuid.uuid4())
    mock.status = overrides.get("status", SimulationStatus.COMPLETED)
    mock.metrics = overrides.get("metrics", {"risk_score": 0.3, "efficiency_score": 0.8})
    mock.impact_analysis = overrides.get("impact_analysis")
    mock.recommendations = overrides.get("recommendations", [])
    mock.execution_time_ms = overrides.get("execution_time_ms", 42)
    mock.error_message = overrides.get("error_message")
    mock.started_at = overrides.get("started_at", datetime.now(UTC))
    mock.completed_at = overrides.get("completed_at", datetime.now(UTC))
    return mock


def _make_modification(**overrides) -> MagicMock:
    mock = MagicMock(spec=ScenarioModification)
    mock.id = overrides.get("id", uuid.uuid4())
    mock.scenario_id = overrides.get("scenario_id", uuid.uuid4())
    mock.modification_type = overrides.get("modification_type", ModificationType.TASK_MODIFY)
    mock.element_id = overrides.get("element_id", "task_1")
    mock.element_name = overrides.get("element_name", "Review Application")
    mock.change_data = overrides.get("change_data")
    mock.template_key = overrides.get("template_key")
    mock.applied_at = overrides.get("applied_at", datetime.now(UTC))
    return mock


def _mock_scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalars_result(items: list) -> MagicMock:
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result = MagicMock()
    result.scalars.return_value = scalars_mock
    return result


# ---------------------------------------------------------------------------
# Modifications CRUD
# ---------------------------------------------------------------------------


class TestModificationsCRUD:
    """Tests for POST/GET/DELETE /scenarios/{id}/modifications."""

    @pytest.mark.asyncio
    async def test_create_modification_201(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        scenario = _make_scenario()
        mock_db_session.execute = AsyncMock(side_effect=[_mock_scalar_result(scenario)])

        response = await client.post(
            f"/api/v1/simulations/scenarios/{scenario.id}/modifications",
            json={
                "modification_type": "task_add",
                "element_id": "new_task",
                "element_name": "New Task",
                "change_data": {"duration": 30},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["modification_type"] == "task_add"
        assert data["element_id"] == "new_task"
        assert data["element_name"] == "New Task"

    @pytest.mark.asyncio
    async def test_create_modification_invalid_template_422(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        scenario = _make_scenario()
        mock_db_session.execute = AsyncMock(side_effect=[_mock_scalar_result(scenario)])

        response = await client.post(
            f"/api/v1/simulations/scenarios/{scenario.id}/modifications",
            json={
                "modification_type": "task_modify",
                "element_id": "t1",
                "element_name": "Task",
                "template_key": "invalid_key",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_modification_valid_template(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        scenario = _make_scenario()
        mock_db_session.execute = AsyncMock(side_effect=[_mock_scalar_result(scenario)])

        response = await client.post(
            f"/api/v1/simulations/scenarios/{scenario.id}/modifications",
            json={
                "modification_type": "task_modify",
                "element_id": "t1",
                "element_name": "Task",
                "template_key": "consolidate_adjacent",
            },
        )
        assert response.status_code == 201
        assert response.json()["template_key"] == "consolidate_adjacent"

    @pytest.mark.asyncio
    async def test_list_modifications(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        scenario = _make_scenario()
        mod = _make_modification(scenario_id=scenario.id)
        mock_db_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_result(scenario),
                _mock_scalars_result([mod]),
            ]
        )

        response = await client.get(f"/api/v1/simulations/scenarios/{scenario.id}/modifications")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["element_name"] == "Review Application"

    @pytest.mark.asyncio
    async def test_delete_modification_204(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        scenario = _make_scenario()
        mod = _make_modification(scenario_id=scenario.id)
        mock_db_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_result(scenario),
                _mock_scalar_result(mod),
            ]
        )

        response = await client.delete(f"/api/v1/simulations/scenarios/{scenario.id}/modifications/{mod.id}")
        assert response.status_code == 204
        mock_db_session.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_modification_wrong_scenario_404(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        scenario = _make_scenario()
        mock_db_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_result(scenario),
                _mock_scalar_result(None),
            ]
        )

        fake_mod_id = uuid.uuid4()
        response = await client.delete(f"/api/v1/simulations/scenarios/{scenario.id}/modifications/{fake_mod_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_modification_scenario_not_found_404(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        mock_db_session.execute = AsyncMock(side_effect=[_mock_scalar_result(None)])
        response = await client.post(
            f"/api/v1/simulations/scenarios/{uuid.uuid4()}/modifications",
            json={
                "modification_type": "task_add",
                "element_id": "t1",
                "element_name": "Task",
            },
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Evidence Coverage
# ---------------------------------------------------------------------------


class TestEvidenceCoverageEndpoint:
    """Tests for GET /scenarios/{id}/evidence-coverage."""

    @staticmethod
    def _setup_neo4j_mock(mock_driver: MagicMock, records: list) -> None:
        """Configure neo4j driver mock to return records from _run_query."""
        neo4j_session_mock = AsyncMock()
        neo4j_result_mock = AsyncMock()
        neo4j_result_mock.data = AsyncMock(return_value=records)
        neo4j_session_mock.run = AsyncMock(return_value=neo4j_result_mock)
        neo4j_session_mock.__aenter__ = AsyncMock(return_value=neo4j_session_mock)
        neo4j_session_mock.__aexit__ = AsyncMock(return_value=None)
        mock_driver.session.return_value = neo4j_session_mock

    @pytest.mark.asyncio
    async def test_coverage_returns_classifications(
        self, client: AsyncClient, mock_db_session: AsyncMock, mock_neo4j_driver: MagicMock
    ) -> None:
        scenario = _make_scenario()

        mock_db_session.execute = AsyncMock(side_effect=[_mock_scalar_result(scenario)])

        self._setup_neo4j_mock(
            mock_neo4j_driver,
            [
                {"id": "e1", "name": "Task A", "evidence_count": 4, "avg_confidence": 0.85},
            ],
        )

        response = await client.get(f"/api/v1/simulations/scenarios/{scenario.id}/evidence-coverage")
        assert response.status_code == 200
        data = response.json()
        assert "elements" in data
        assert "bright_count" in data
        assert "aggregate_confidence" in data

    @pytest.mark.asyncio
    async def test_coverage_404_for_missing_scenario(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        mock_db_session.execute = AsyncMock(side_effect=[_mock_scalar_result(None)])

        response = await client.get(f"/api/v1/simulations/scenarios/{uuid.uuid4()}/evidence-coverage")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Scenario Comparison
# ---------------------------------------------------------------------------


class TestCompareScenarios:
    """Tests for GET /scenarios/{id}/compare?ids=..."""

    @staticmethod
    def _setup_neo4j_mock(mock_driver: MagicMock, records: list | None = None) -> None:
        neo4j_session_mock = AsyncMock()
        neo4j_result_mock = AsyncMock()
        neo4j_result_mock.data = AsyncMock(return_value=records or [])
        neo4j_session_mock.run = AsyncMock(return_value=neo4j_result_mock)
        neo4j_session_mock.__aenter__ = AsyncMock(return_value=neo4j_session_mock)
        neo4j_session_mock.__aexit__ = AsyncMock(return_value=None)
        mock_driver.session.return_value = neo4j_session_mock

    @pytest.mark.asyncio
    async def test_compare_404_baseline_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        mock_db_session.execute = AsyncMock(side_effect=[_mock_scalar_result(None)])

        response = await client.get(f"/api/v1/simulations/scenarios/{uuid.uuid4()}/compare?ids={uuid.uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_compare_happy_path(
        self, client: AsyncClient, mock_db_session: AsyncMock, mock_neo4j_driver: MagicMock
    ) -> None:
        baseline = _make_scenario(name="Baseline")
        alt_id = uuid.uuid4()
        alt_scenario = _make_scenario(id=alt_id, name="Alt A", engagement_id=baseline.engagement_id)
        baseline_result = _make_result(
            scenario_id=baseline.id,
            metrics={"risk_score": 0.3, "efficiency_score": 0.8},
        )
        alt_result = _make_result(
            scenario_id=alt_id,
            metrics={"risk_score": 0.2, "efficiency_score": 0.85},
        )

        self._setup_neo4j_mock(mock_neo4j_driver)

        mock_db_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_result(baseline),  # fetch baseline
                _mock_scalar_result(baseline_result),  # baseline result
                _mock_scalars_result([alt_scenario]),  # batch-fetch comparison scenarios
                _mock_scalars_result([alt_result]),  # batch-fetch latest results
            ]
        )

        response = await client.get(f"/api/v1/simulations/scenarios/{baseline.id}/compare?ids={alt_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["baseline_name"] == "Baseline"
        assert len(data["comparisons"]) == 1
        assert data["comparisons"][0]["scenario_name"] == "Alt A"
        assert data["comparisons"][0]["deltas"] is not None

    @pytest.mark.asyncio
    async def test_compare_missing_result_returns_null_deltas(
        self, client: AsyncClient, mock_db_session: AsyncMock, mock_neo4j_driver: MagicMock
    ) -> None:
        baseline = _make_scenario(name="Baseline")
        alt_id = uuid.uuid4()
        alt_scenario = _make_scenario(id=alt_id, name="Alt B", engagement_id=baseline.engagement_id)

        self._setup_neo4j_mock(mock_neo4j_driver)

        mock_db_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_result(baseline),  # fetch baseline
                _mock_scalar_result(None),  # no baseline result
                _mock_scalars_result([alt_scenario]),  # batch-fetch comparison scenarios
                _mock_scalars_result([]),  # batch-fetch latest results (none)
            ]
        )

        response = await client.get(f"/api/v1/simulations/scenarios/{baseline.id}/compare?ids={alt_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["comparisons"][0]["deltas"] is None

    @pytest.mark.asyncio
    async def test_compare_invalid_ids_422(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        baseline = _make_scenario()
        mock_db_session.execute = AsyncMock(side_effect=[_mock_scalar_result(baseline)])

        response = await client.get(f"/api/v1/simulations/scenarios/{baseline.id}/compare?ids=not-a-uuid")
        assert response.status_code == 422
