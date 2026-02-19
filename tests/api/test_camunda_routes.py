"""Tests for Camunda (CIB7) API routes."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def mock_camunda_client():
    """Create a mock Camunda client."""
    client = AsyncMock()
    client.list_deployments = AsyncMock(return_value=[{"id": "dep-1", "name": "test"}])
    client.deploy_process = AsyncMock(return_value={"id": "dep-2", "name": "new"})
    client.list_process_definitions = AsyncMock(return_value=[{"id": "proc:1", "key": "myProcess"}])
    client.start_process = AsyncMock(return_value={"id": "inst-1", "definitionId": "proc:1"})
    client.get_process_instances = AsyncMock(return_value=[{"id": "inst-1", "ended": False}])
    client.get_tasks = AsyncMock(return_value=[{"id": "task-1", "name": "Review"}])
    return client


@pytest.fixture
def app_with_camunda(test_app, mock_camunda_client):
    """Attach mock Camunda client to test app."""
    test_app.state.camunda_client = mock_camunda_client
    return test_app


class TestListDeployments:
    """Tests for GET /api/v1/camunda/deployments."""

    @pytest.mark.asyncio
    async def test_list_deployments_success(self, client, app_with_camunda, mock_camunda_client):
        response = await client.get("/api/v1/camunda/deployments")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "dep-1"
        mock_camunda_client.list_deployments.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_deployments_engine_error(self, client, app_with_camunda, mock_camunda_client):
        mock_camunda_client.list_deployments.side_effect = Exception("Connection refused")
        response = await client.get("/api/v1/camunda/deployments")
        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_list_deployments_no_engine(self, client, test_app):
        # Remove camunda_client from state
        if hasattr(test_app.state, "camunda_client"):
            delattr(test_app.state, "camunda_client")
        response = await client.get("/api/v1/camunda/deployments")
        assert response.status_code == 503


class TestDeployProcess:
    """Tests for POST /api/v1/camunda/deploy."""

    @pytest.mark.asyncio
    async def test_deploy_process_success(self, client, app_with_camunda, mock_camunda_client):
        bpmn_content = b"<bpmn:definitions>test</bpmn:definitions>"
        response = await client.post(
            "/api/v1/camunda/deploy",
            files={"file": ("process.bpmn", io.BytesIO(bpmn_content), "application/xml")},
            data={"deployment_name": "test-deploy"},
        )
        assert response.status_code == 200
        mock_camunda_client.deploy_process.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deploy_process_engine_error(self, client, app_with_camunda, mock_camunda_client):
        mock_camunda_client.deploy_process.side_effect = Exception("Deploy failed")
        response = await client.post(
            "/api/v1/camunda/deploy",
            files={"file": ("process.bpmn", io.BytesIO(b"<bpmn/>"), "application/xml")},
        )
        assert response.status_code == 502


class TestProcessDefinitions:
    """Tests for GET /api/v1/camunda/process-definitions."""

    @pytest.mark.asyncio
    async def test_list_process_definitions(self, client, app_with_camunda, mock_camunda_client):
        response = await client.get("/api/v1/camunda/process-definitions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["key"] == "myProcess"

    @pytest.mark.asyncio
    async def test_list_process_definitions_error(self, client, app_with_camunda, mock_camunda_client):
        mock_camunda_client.list_process_definitions.side_effect = Exception("Timeout")
        response = await client.get("/api/v1/camunda/process-definitions")
        assert response.status_code == 502


class TestStartProcess:
    """Tests for POST /api/v1/camunda/process/{key}/start."""

    @pytest.mark.asyncio
    async def test_start_process_success(self, client, app_with_camunda, mock_camunda_client):
        response = await client.post(
            "/api/v1/camunda/process/myProcess/start",
            json={"variables": {"assignee": "user1"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "inst-1"
        mock_camunda_client.start_process.assert_awaited_once_with("myProcess", variables={"assignee": "user1"})

    @pytest.mark.asyncio
    async def test_start_process_no_variables(self, client, app_with_camunda, mock_camunda_client):
        response = await client.post(
            "/api/v1/camunda/process/myProcess/start",
            json={},
        )
        assert response.status_code == 200
        mock_camunda_client.start_process.assert_awaited_once_with("myProcess", variables=None)

    @pytest.mark.asyncio
    async def test_start_process_error(self, client, app_with_camunda, mock_camunda_client):
        mock_camunda_client.start_process.side_effect = Exception("Process not found")
        response = await client.post(
            "/api/v1/camunda/process/badKey/start",
            json={},
        )
        assert response.status_code == 502


class TestProcessInstances:
    """Tests for GET /api/v1/camunda/process-instances."""

    @pytest.mark.asyncio
    async def test_get_instances_active(self, client, app_with_camunda, mock_camunda_client):
        response = await client.get("/api/v1/camunda/process-instances?active=true")
        assert response.status_code == 200
        mock_camunda_client.get_process_instances.assert_awaited_once_with(active=True)

    @pytest.mark.asyncio
    async def test_get_instances_all(self, client, app_with_camunda, mock_camunda_client):
        response = await client.get("/api/v1/camunda/process-instances?active=false")
        assert response.status_code == 200
        mock_camunda_client.get_process_instances.assert_awaited_once_with(active=False)

    @pytest.mark.asyncio
    async def test_get_instances_error(self, client, app_with_camunda, mock_camunda_client):
        mock_camunda_client.get_process_instances.side_effect = Exception("Error")
        response = await client.get("/api/v1/camunda/process-instances")
        assert response.status_code == 502


class TestGetTasks:
    """Tests for GET /api/v1/camunda/tasks."""

    @pytest.mark.asyncio
    async def test_get_tasks_all(self, client, app_with_camunda, mock_camunda_client):
        response = await client.get("/api/v1/camunda/tasks")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Review"
        mock_camunda_client.get_tasks.assert_awaited_once_with(assignee=None)

    @pytest.mark.asyncio
    async def test_get_tasks_with_assignee(self, client, app_with_camunda, mock_camunda_client):
        response = await client.get("/api/v1/camunda/tasks?assignee=user1")
        assert response.status_code == 200
        mock_camunda_client.get_tasks.assert_awaited_once_with(assignee="user1")

    @pytest.mark.asyncio
    async def test_get_tasks_error(self, client, app_with_camunda, mock_camunda_client):
        mock_camunda_client.get_tasks.side_effect = Exception("Error")
        response = await client.get("/api/v1/camunda/tasks")
        assert response.status_code == 502
