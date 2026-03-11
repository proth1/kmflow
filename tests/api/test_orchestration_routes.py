"""Tests for BPMN Workflow Orchestration API routes."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.routes.orchestration import (
    L4_WORKFLOW_FILES,
    PLATFORM_BPMN_DIR,
    cancel_process_instance,
    deploy_all_workflows,
    get_process_instance_detail,
    list_process_instances,
    retry_instance_incidents,
)


def _mock_request(camunda_client: AsyncMock | None = None) -> MagicMock:
    request = MagicMock()
    request.app.state.camunda_client = camunda_client
    return request


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


class TestDeployAllWorkflows:
    @pytest.mark.asyncio
    async def test_deploys_existing_files(self) -> None:
        mock_client = AsyncMock()
        mock_client.deploy_process = AsyncMock(
            return_value={
                "id": "dep-1",
                "name": "Test",
                "deployedProcessDefinitions": {"Process_1": {}},
            }
        )

        request = _mock_request(mock_client)

        with patch("src.api.routes.orchestration.PLATFORM_BPMN_DIR", PLATFORM_BPMN_DIR):
            result = await deploy_all_workflows(request, _mock_user())

        assert result["total"] == len(L4_WORKFLOW_FILES)
        assert result["deployed"] + result["failed"] == result["total"]

    @pytest.mark.asyncio
    async def test_handles_missing_files(self) -> None:
        mock_client = AsyncMock()
        request = _mock_request(mock_client)

        # Use a non-existent directory
        with patch("src.api.routes.orchestration.PLATFORM_BPMN_DIR", Path("/nonexistent")):
            result = await deploy_all_workflows(request, _mock_user())

        assert result["deployed"] == 0
        assert result["failed"] == len(L4_WORKFLOW_FILES)

    @pytest.mark.asyncio
    async def test_handles_deployment_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.deploy_process = AsyncMock(side_effect=ConnectionError("offline"))
        request = _mock_request(mock_client)

        result = await deploy_all_workflows(request, _mock_user())

        assert result["deployed"] == 0
        assert len(result["errors"]) > 0


class TestListProcessInstances:
    @pytest.mark.asyncio
    async def test_returns_enriched_instances(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_process_instances = AsyncMock(
            return_value=[
                {"id": "pid-1", "businessKey": "ENG-001", "definitionId": "def-1", "suspended": False},
            ]
        )
        mock_client.get_incidents = AsyncMock(return_value=[{"id": "inc-1"}])

        request = _mock_request(mock_client)
        result = await list_process_instances(request, True, _mock_user())

        assert result["total"] == 1
        assert result["instances"][0]["incident_count"] == 1
        assert result["instances"][0]["business_key"] == "ENG-001"

    @pytest.mark.asyncio
    async def test_handles_engine_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_process_instances = AsyncMock(side_effect=ConnectionError("down"))

        request = _mock_request(mock_client)
        with pytest.raises(Exception) as exc_info:
            await list_process_instances(request, True, _mock_user())

        assert exc_info.value.status_code == 502


class TestGetProcessInstanceDetail:
    @pytest.mark.asyncio
    async def test_returns_activity_tree_and_incidents(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_activity_instances = AsyncMock(
            return_value={"id": "pid:1", "activityId": "Process_1", "childActivityInstances": []}
        )
        mock_client.get_incidents = AsyncMock(return_value=[])

        request = _mock_request(mock_client)
        result = await get_process_instance_detail("pid-1", request, _mock_user())

        assert result["instance_id"] == "pid-1"
        assert result["incident_count"] == 0
        assert "activity_tree" in result


class TestRetryInstanceIncidents:
    @pytest.mark.asyncio
    async def test_retries_incidents(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_incidents = AsyncMock(
            return_value=[
                {"id": "inc-1", "configuration": "ext-task-1"},
            ]
        )
        mock_client.retry_incident = AsyncMock()

        request = _mock_request(mock_client)
        result = await retry_instance_incidents("pid-1", request, _mock_user())

        assert result["retried"] == 1
        assert result["total_incidents"] == 1

    @pytest.mark.asyncio
    async def test_no_incidents(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_incidents = AsyncMock(return_value=[])

        request = _mock_request(mock_client)
        result = await retry_instance_incidents("pid-1", request, _mock_user())

        assert result["retried"] == 0


class TestCancelProcessInstance:
    @pytest.mark.asyncio
    async def test_cancels_instance(self) -> None:
        mock_client = AsyncMock()
        mock_client.delete_process_instance = AsyncMock()

        request = _mock_request(mock_client)
        result = await cancel_process_instance("pid-1", request, _mock_user())

        assert result["status"] == "cancelled"
        mock_client.delete_process_instance.assert_awaited_once_with("pid-1")


class TestPlatformBpmnDir:
    def test_bpmn_dir_exists(self) -> None:
        assert PLATFORM_BPMN_DIR.exists()

    def test_l4_workflow_count(self) -> None:
        assert len(L4_WORKFLOW_FILES) == 7

    def test_all_bpmn_files_exist(self) -> None:
        for filename in L4_WORKFLOW_FILES:
            assert (PLATFORM_BPMN_DIR / filename).exists(), f"Missing: {filename}"
