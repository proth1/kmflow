"""Tests for Camunda CIB7 REST API client — external task and instance methods."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.integrations.camunda import CamundaClient


@pytest.fixture
def client() -> CamundaClient:
    return CamundaClient("http://localhost:8080/engine-rest")


class TestSerializeVariables:
    def test_string(self) -> None:
        result = CamundaClient._serialize_variables({"name": "hello"})
        assert result["name"] == {"value": "hello", "type": "String"}

    def test_integer(self) -> None:
        result = CamundaClient._serialize_variables({"count": 42})
        assert result["count"] == {"value": 42, "type": "Long"}

    def test_float(self) -> None:
        result = CamundaClient._serialize_variables({"score": 0.95})
        assert result["score"] == {"value": 0.95, "type": "Double"}

    def test_boolean(self) -> None:
        result = CamundaClient._serialize_variables({"active": True})
        assert result["active"] == {"value": True, "type": "Boolean"}

    def test_dict_as_json(self) -> None:
        result = CamundaClient._serialize_variables({"data": {"key": "val"}})
        assert result["data"]["type"] == "Json"
        assert '"key"' in result["data"]["value"]

    def test_list_as_json(self) -> None:
        result = CamundaClient._serialize_variables({"items": [1, 2, 3]})
        assert result["items"]["type"] == "Json"


class TestFetchAndLock:
    @pytest.mark.asyncio
    async def test_fetch_and_lock_builds_correct_body(self, client: CamundaClient) -> None:
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=[]) as mock_req:
            result = await client.fetch_and_lock_external_tasks(
                worker_id="test-worker",
                topics=[{"topicName": "classify-evidence"}],
                max_tasks=3,
            )

        mock_req.assert_awaited_once()
        call_args = mock_req.call_args
        assert call_args[0] == ("POST", "/external-task/fetchAndLock")
        body = call_args[1]["json"]
        assert body["workerId"] == "test-worker"
        assert body["maxTasks"] == 3
        assert body["topics"][0]["topicName"] == "classify-evidence"
        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_and_lock_multiple_topics(self, client: CamundaClient) -> None:
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=[]) as mock_req:
            await client.fetch_and_lock_external_tasks(
                worker_id="w1",
                topics=[
                    {"topicName": "topic-a"},
                    {"topicName": "topic-b", "lockDuration": 60000},
                ],
            )

        body = mock_req.call_args[1]["json"]
        assert len(body["topics"]) == 2
        assert body["topics"][1]["lockDuration"] == 60000


class TestCompleteExternalTask:
    @pytest.mark.asyncio
    async def test_complete_with_variables(self, client: CamundaClient) -> None:
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            await client.complete_external_task(
                task_id="task-123",
                worker_id="w1",
                variables={"result": "success", "count": 5},
            )

        call_args = mock_req.call_args
        assert call_args[0] == ("POST", "/external-task/task-123/complete")
        body = call_args[1]["json"]
        assert body["workerId"] == "w1"
        assert body["variables"]["result"]["type"] == "String"
        assert body["variables"]["count"]["type"] == "Long"

    @pytest.mark.asyncio
    async def test_complete_without_variables(self, client: CamundaClient) -> None:
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            await client.complete_external_task(task_id="t1", worker_id="w1")

        body = mock_req.call_args[1]["json"]
        assert "variables" not in body


class TestFailExternalTask:
    @pytest.mark.asyncio
    async def test_fail_sends_error_message(self, client: CamundaClient) -> None:
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            await client.fail_external_task(
                task_id="t1",
                worker_id="w1",
                error_message="Something went wrong",
                retries=2,
            )

        body = mock_req.call_args[1]["json"]
        assert body["errorMessage"] == "Something went wrong"
        assert body["retries"] == 2

    @pytest.mark.asyncio
    async def test_fail_truncates_long_message(self, client: CamundaClient) -> None:
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            await client.fail_external_task(task_id="t1", worker_id="w1", error_message="x" * 1000)

        body = mock_req.call_args[1]["json"]
        assert len(body["errorMessage"]) == 500


class TestBpmnError:
    @pytest.mark.asyncio
    async def test_report_bpmn_error(self, client: CamundaClient) -> None:
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            await client.report_bpmn_error(task_id="t1", worker_id="w1", error_code="VALIDATION_FAILED")

        call_args = mock_req.call_args
        assert call_args[0] == ("POST", "/external-task/t1/bpmnError")
        assert call_args[1]["json"]["errorCode"] == "VALIDATION_FAILED"


class TestProcessInstanceMethods:
    @pytest.mark.asyncio
    async def test_get_activity_instances(self, client: CamundaClient) -> None:
        tree = {"id": "pid:1", "activityId": "Process_1", "childActivityInstances": []}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=tree):
            result = await client.get_activity_instances("pid-123")

        assert result["id"] == "pid:1"

    @pytest.mark.asyncio
    async def test_get_incidents(self, client: CamundaClient) -> None:
        incidents = [{"id": "inc-1", "processInstanceId": "pid-123"}]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=incidents) as mock_req:
            result = await client.get_incidents(process_instance_id="pid-123")

        assert len(result) == 1
        assert mock_req.call_args[1]["params"]["processInstanceId"] == "pid-123"

    @pytest.mark.asyncio
    async def test_delete_process_instance(self, client: CamundaClient) -> None:
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            await client.delete_process_instance("pid-123")

        assert mock_req.call_args[0] == ("DELETE", "/process-instance/pid-123")
