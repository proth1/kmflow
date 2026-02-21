"""Tests for the Camunda (CIB7) REST API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.integrations.camunda import CamundaClient


def _make_response(
    status_code: int = 200,
    json_data: object = None,
) -> httpx.Response:
    """Build a minimal httpx.Response for mocking."""
    return httpx.Response(
        status_code=status_code,
        json=json_data if json_data is not None else {},
        request=httpx.Request("GET", "https://camunda.example.com"),
    )


# =============================================================================
# CamundaClient construction
# =============================================================================


class TestCamundaClientInit:
    """Tests for CamundaClient initialisation."""

    def test_base_url_trailing_slash_stripped(self) -> None:
        client = CamundaClient("http://localhost:8080/engine-rest/")
        assert client.base_url == "http://localhost:8080/engine-rest"

    def test_base_url_no_trailing_slash(self) -> None:
        client = CamundaClient("http://localhost:8080/engine-rest")
        assert client.base_url == "http://localhost:8080/engine-rest"

    def test_default_timeout(self) -> None:
        client = CamundaClient("http://localhost:8080")
        assert client.timeout == 30.0

    def test_custom_timeout(self) -> None:
        client = CamundaClient("http://localhost:8080", timeout=60.0)
        assert client.timeout == 60.0


# =============================================================================
# _request (internal helper)
# =============================================================================


@pytest.mark.asyncio
class TestCamundaClientRequest:
    """Tests for the internal _request method."""

    async def test_request_returns_json_on_success(self) -> None:
        """A 200 response returns parsed JSON."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        mock_response = _make_response(200, {"id": "proc-1"})

        with patch("src.integrations.camunda.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.request = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_http

            result = await client._request("GET", "/process-definition")

        assert result == {"id": "proc-1"}

    async def test_request_returns_none_on_204(self) -> None:
        """A 204 No Content response returns None."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        mock_response = _make_response(204, {})

        with patch("src.integrations.camunda.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.request = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_http

            result = await client._request("POST", "/task/t1/complete")

        assert result is None

    async def test_request_raises_on_http_error(self) -> None:
        """Non-2xx responses propagate as HTTPStatusError."""
        client = CamundaClient("http://localhost:8080/engine-rest")

        with patch("src.integrations.camunda.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            # raise_for_status is called on the returned response
            bad_response = _make_response(500, {"type": "InternalError"})
            mock_http.request = AsyncMock(return_value=bad_response)
            mock_cls.return_value = mock_http

            with pytest.raises(httpx.HTTPStatusError):
                await client._request("GET", "/deployment")

    async def test_request_builds_correct_url(self) -> None:
        """The URL sent to httpx is base_url + path."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        mock_response = _make_response(200, [])
        captured_url: list[str] = []

        with patch("src.integrations.camunda.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)

            async def capture_request(method: str, url: str, **kwargs: object) -> httpx.Response:
                captured_url.append(url)
                return mock_response

            mock_http.request = capture_request
            mock_cls.return_value = mock_http

            await client._request("GET", "/engine")

        assert captured_url[0] == "http://localhost:8080/engine-rest/engine"


# =============================================================================
# verify_connectivity
# =============================================================================


@pytest.mark.asyncio
class TestVerifyConnectivity:
    """Tests for verify_connectivity()."""

    async def test_returns_true_when_engine_list_non_empty(self) -> None:
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [{"name": "default"}]
            result = await client.verify_connectivity()
        assert result is True
        mock_req.assert_awaited_once_with("GET", "/engine")

    async def test_returns_false_when_engine_list_empty(self) -> None:
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = []
            result = await client.verify_connectivity()
        assert result is False

    async def test_returns_false_when_engine_returns_non_list(self) -> None:
        """A non-list response (unexpected shape) is treated as unreachable."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"name": "default"}
            result = await client.verify_connectivity()
        assert result is False

    async def test_returns_false_on_exception(self) -> None:
        """Any exception during the check returns False without re-raising."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.ConnectError("connection refused")
            result = await client.verify_connectivity()
        assert result is False

    async def test_returns_false_on_http_status_error(self) -> None:
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.HTTPStatusError(
                "500",
                request=httpx.Request("GET", "http://localhost:8080/engine-rest/engine"),
                response=_make_response(500),
            )
            result = await client.verify_connectivity()
        assert result is False


# =============================================================================
# list_deployments
# =============================================================================


@pytest.mark.asyncio
class TestListDeployments:
    """Tests for list_deployments()."""

    async def test_returns_deployment_list(self) -> None:
        client = CamundaClient("http://localhost:8080/engine-rest")
        deployments = [{"id": "dep-1", "name": "MyProcess"}, {"id": "dep-2", "name": "OtherProcess"}]
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = deployments
            result = await client.list_deployments()
        assert result == deployments
        mock_req.assert_awaited_once_with("GET", "/deployment")

    async def test_returns_empty_list(self) -> None:
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = []
            result = await client.list_deployments()
        assert result == []


# =============================================================================
# deploy_process
# =============================================================================


@pytest.mark.asyncio
class TestDeployProcess:
    """Tests for deploy_process()."""

    async def test_deploy_success_returns_deployment_dict(self) -> None:
        """Successful deployment returns the JSON response from CIB7."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        bpmn_bytes = b"<definitions>...</definitions>"
        expected = {"id": "dep-new", "name": "MyProcess", "deploymentTime": "2024-01-01T00:00:00"}

        with patch("src.integrations.camunda.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            ok_response = _make_response(200, expected)
            mock_http.post = AsyncMock(return_value=ok_response)
            mock_cls.return_value = mock_http

            result = await client.deploy_process("MyProcess", bpmn_bytes)

        assert result == expected

    async def test_deploy_sends_correct_deployment_name(self) -> None:
        """The deployment-name field in the multipart body matches the name arg."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        captured_kwargs: list[dict] = []

        with patch("src.integrations.camunda.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)

            async def capture_post(url: str, **kwargs: object) -> httpx.Response:
                captured_kwargs.append(dict(kwargs))
                return _make_response(200, {"id": "dep-1"})

            mock_http.post = capture_post
            mock_cls.return_value = mock_http

            await client.deploy_process("TargetProcess", b"<xml/>", filename="target.bpmn")

        data = captured_kwargs[0]["data"]
        assert data["deployment-name"] == "TargetProcess"
        assert data["enable-duplicate-filtering"] == "true"

    async def test_deploy_uses_custom_filename(self) -> None:
        """The filename parameter controls the multipart file entry name."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        captured_files: list[dict] = []

        with patch("src.integrations.camunda.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)

            async def capture_post(url: str, **kwargs: object) -> httpx.Response:
                captured_files.append(kwargs.get("files", {}))
                return _make_response(200, {"id": "dep-1"})

            mock_http.post = capture_post
            mock_cls.return_value = mock_http

            await client.deploy_process("P", b"<xml/>", filename="custom.bpmn")

        name, _content, _mime = captured_files[0]["data"]
        assert name == "custom.bpmn"

    async def test_deploy_raises_on_http_error(self) -> None:
        """A non-2xx response from deploy propagates as HTTPStatusError."""
        client = CamundaClient("http://localhost:8080/engine-rest")

        with patch("src.integrations.camunda.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            bad_response = _make_response(400, {"message": "Bad request"})
            mock_http.post = AsyncMock(return_value=bad_response)
            mock_cls.return_value = mock_http

            with pytest.raises(httpx.HTTPStatusError):
                await client.deploy_process("BadProcess", b"<invalid/>")


# =============================================================================
# list_process_definitions
# =============================================================================


@pytest.mark.asyncio
class TestListProcessDefinitions:
    """Tests for list_process_definitions()."""

    async def test_returns_definitions_list(self) -> None:
        client = CamundaClient("http://localhost:8080/engine-rest")
        definitions = [{"id": "myProc:1", "key": "myProc", "version": 1}]
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = definitions
            result = await client.list_process_definitions()
        assert result == definitions
        mock_req.assert_awaited_once_with(
            "GET",
            "/process-definition",
            params={"latestVersion": "true"},
        )

    async def test_passes_latest_version_param(self) -> None:
        """list_process_definitions always filters to latest version."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = []
            await client.list_process_definitions()

        _method, _path = mock_req.call_args[0]
        params = mock_req.call_args[1]["params"]
        assert params["latestVersion"] == "true"


# =============================================================================
# start_process
# =============================================================================


@pytest.mark.asyncio
class TestStartProcess:
    """Tests for start_process()."""

    async def test_start_process_no_variables(self) -> None:
        """Starting a process without variables sends an empty body."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        instance = {"id": "inst-1", "definitionId": "myProc:1"}
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = instance
            result = await client.start_process("myProc")
        assert result == instance
        mock_req.assert_awaited_once_with(
            "POST",
            "/process-definition/key/myProc/start",
            json={},
        )

    async def test_start_process_with_variables(self) -> None:
        """Variables are serialised into Camunda's typed-value format."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"id": "inst-2"}
            await client.start_process("myProc", variables={"engagementId": "eng-1", "priority": "high"})

        _method, _path = mock_req.call_args[0]
        body = mock_req.call_args[1]["json"]
        assert "variables" in body
        assert body["variables"]["engagementId"] == {"value": "eng-1", "type": "String"}
        assert body["variables"]["priority"] == {"value": "high", "type": "String"}

    async def test_start_process_uses_correct_key_path(self) -> None:
        """The process definition key is embedded in the URL path."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"id": "inst-3"}
            await client.start_process("engagementLifecycle")

        _method, path = mock_req.call_args[0]
        assert path == "/process-definition/key/engagementLifecycle/start"


# =============================================================================
# get_process_instances
# =============================================================================


@pytest.mark.asyncio
class TestGetProcessInstances:
    """Tests for get_process_instances()."""

    async def test_active_instances_default(self) -> None:
        """Without args, requests only active instances."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [{"id": "pi-1"}]
            result = await client.get_process_instances()
        assert result == [{"id": "pi-1"}]
        mock_req.assert_awaited_once_with(
            "GET",
            "/process-instance",
            params={"active": "true"},
        )

    async def test_all_instances_when_active_false(self) -> None:
        """active=False omits the active filter parameter."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = []
            await client.get_process_instances(active=False)

        _method, _path = mock_req.call_args[0]
        params = mock_req.call_args[1]["params"]
        assert "active" not in params

    async def test_returns_empty_list_when_no_instances(self) -> None:
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = []
            result = await client.get_process_instances()
        assert result == []


# =============================================================================
# get_tasks
# =============================================================================


@pytest.mark.asyncio
class TestGetTasks:
    """Tests for get_tasks()."""

    async def test_all_tasks_no_assignee(self) -> None:
        """Without an assignee, requests all tasks."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        tasks = [{"id": "task-1", "name": "Review"}, {"id": "task-2", "name": "Approve"}]
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = tasks
            result = await client.get_tasks()
        assert result == tasks
        mock_req.assert_awaited_once_with("GET", "/task", params={})

    async def test_tasks_filtered_by_assignee(self) -> None:
        """Passing an assignee adds it to the query params."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [{"id": "task-3"}]
            await client.get_tasks(assignee="alice@example.com")

        _method, _path = mock_req.call_args[0]
        params = mock_req.call_args[1]["params"]
        assert params["assignee"] == "alice@example.com"

    async def test_returns_empty_list_when_no_tasks(self) -> None:
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = []
            result = await client.get_tasks()
        assert result == []


# =============================================================================
# complete_task
# =============================================================================


@pytest.mark.asyncio
class TestCompleteTask:
    """Tests for complete_task()."""

    async def test_complete_task_no_variables(self) -> None:
        """Completing a task without variables posts an empty body and returns None."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            result = await client.complete_task("task-abc")
        assert result is None
        mock_req.assert_awaited_once_with(
            "POST",
            "/task/task-abc/complete",
            json={},
        )

    async def test_complete_task_with_variables(self) -> None:
        """Variables are serialised into Camunda's typed-value format."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            await client.complete_task("task-xyz", variables={"approved": "true", "comment": "LGTM"})

        _method, _path = mock_req.call_args[0]
        body = mock_req.call_args[1]["json"]
        assert "variables" in body
        assert body["variables"]["approved"] == {"value": "true", "type": "String"}
        assert body["variables"]["comment"] == {"value": "LGTM", "type": "String"}

    async def test_complete_task_uses_correct_task_id_path(self) -> None:
        """The task ID is embedded in the URL path."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            await client.complete_task("my-task-id-123")

        _method, path = mock_req.call_args[0]
        assert path == "/task/my-task-id-123/complete"

    async def test_complete_task_raises_on_not_found(self) -> None:
        """A 404 from _request propagates (task not found)."""
        client = CamundaClient("http://localhost:8080/engine-rest")
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.HTTPStatusError(
                "404",
                request=httpx.Request("POST", "http://localhost:8080/engine-rest/task/gone/complete"),
                response=_make_response(404),
            )
            with pytest.raises(httpx.HTTPStatusError):
                await client.complete_task("gone")
