"""Tests for simulation routes.

Tests the /api/v1/simulations endpoints for creating scenarios,
running simulations, and retrieving results.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.models import SimulationResult, SimulationScenario, SimulationStatus, SimulationType


class TestScenarioRoutes:
    """Tests for simulation scenario routes."""

    @pytest.mark.asyncio
    async def test_create_scenario(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test creating a simulation scenario."""
        scenario_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        def refresh_side_effect(obj: Any) -> None:
            if isinstance(obj, SimulationScenario):
                obj.id = scenario_id
                obj.created_at = datetime.now(timezone.utc)

        mock_db_session.refresh.side_effect = refresh_side_effect

        response = await client.post(
            "/api/v1/simulations/scenarios",
            json={
                "engagement_id": str(engagement_id),
                "name": "Test Scenario",
                "simulation_type": "what_if",
                "parameters": {"resources": 10},
                "description": "A test scenario",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Scenario"
        assert data["simulation_type"] == "what_if"

    @pytest.mark.asyncio
    async def test_list_scenarios(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test listing simulation scenarios."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = await client.get("/api/v1/simulations/scenarios")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_scenario(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test getting a scenario by ID."""
        scenario_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        mock_scenario = MagicMock(spec=SimulationScenario)
        mock_scenario.id = scenario_id
        mock_scenario.engagement_id = engagement_id
        mock_scenario.process_model_id = None
        mock_scenario.name = "Test Scenario"
        mock_scenario.simulation_type = SimulationType.WHAT_IF
        mock_scenario.parameters = {"resources": 10}
        mock_scenario.description = "A test scenario"
        mock_scenario.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_scenario
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/simulations/scenarios/{scenario_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(scenario_id)

    @pytest.mark.asyncio
    async def test_get_scenario_not_found(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test getting a scenario that does not exist."""
        scenario_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/simulations/scenarios/{scenario_id}")
        assert response.status_code == 404


class TestRunSimulation:
    """Tests for running simulation scenarios."""

    @pytest.mark.asyncio
    async def test_run_scenario(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test running a simulation scenario creates a result."""
        scenario_id = uuid.uuid4()
        result_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        mock_scenario = MagicMock(spec=SimulationScenario)
        mock_scenario.id = scenario_id
        mock_scenario.engagement_id = engagement_id
        mock_scenario.simulation_type = SimulationType.WHAT_IF
        mock_scenario.parameters = {
            "process_graph": {"elements": [], "connections": []},
            "element_changes": {},
        }

        # First execute returns the scenario, subsequent ones handle result operations
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_scenario
        mock_db_session.execute.return_value = mock_result

        def refresh_side_effect(obj: Any) -> None:
            if isinstance(obj, SimulationResult):
                if obj.id is None:
                    obj.id = result_id
                obj.started_at = datetime.now(timezone.utc)
                obj.completed_at = datetime.now(timezone.utc)

        mock_db_session.refresh.side_effect = refresh_side_effect

        response = await client.post(f"/api/v1/simulations/scenarios/{scenario_id}/run")
        assert response.status_code == 200
        data = response.json()
        assert data["scenario_id"] == str(scenario_id)
        assert "status" in data

    @pytest.mark.asyncio
    async def test_run_scenario_not_found(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test running a scenario that does not exist."""
        scenario_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.post(f"/api/v1/simulations/scenarios/{scenario_id}/run")
        assert response.status_code == 404


class TestResultRoutes:
    """Tests for simulation result routes."""

    @pytest.mark.asyncio
    async def test_list_results(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test listing simulation results."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = await client.get("/api/v1/simulations/results")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_result(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test getting a simulation result by ID."""
        result_id = uuid.uuid4()
        scenario_id = uuid.uuid4()

        mock_sim_result = MagicMock(spec=SimulationResult)
        mock_sim_result.id = result_id
        mock_sim_result.scenario_id = scenario_id
        mock_sim_result.status = SimulationStatus.COMPLETED
        mock_sim_result.metrics = {"throughput": 100}
        mock_sim_result.impact_analysis = {}
        mock_sim_result.recommendations = []
        mock_sim_result.execution_time_ms = 1000
        mock_sim_result.error_message = None
        mock_sim_result.started_at = datetime.now(timezone.utc)
        mock_sim_result.completed_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sim_result
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/simulations/results/{result_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(result_id)

    @pytest.mark.asyncio
    async def test_get_result_not_found(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test getting a result that does not exist."""
        result_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/simulations/results/{result_id}")
        assert response.status_code == 404
