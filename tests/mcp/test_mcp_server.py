"""Tests for MCP server tool dispatch and streaming endpoints."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Shared fixture: configure mock DB to pass MCP auth for all tests here
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mcp_auth_key(test_app: Any, mock_db_session: AsyncMock) -> None:
    """Make every request in this module authenticate successfully."""
    mock_key = MagicMock()
    mock_key.key_id = "kmflow_srvtest"
    mock_key.key_hash = hashlib.sha256(b"srvsecret").hexdigest()
    mock_key.is_active = True
    mock_key.user_id = uuid.uuid4()
    mock_key.client_name = "server-test-client"
    mock_key.expires_at = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_key
    mock_result.scalar.return_value = 0
    mock_result.scalars.return_value.all.return_value = []
    mock_db_session.execute = AsyncMock(return_value=mock_result)


_AUTH_HEADER = {"Authorization": "Bearer kmflow_srvtest.srvsecret"}


# =============================================================================
# GET /mcp/info
# =============================================================================


@pytest.mark.asyncio
class TestMCPServerInfo:
    """Tests for GET /mcp/info."""

    async def test_info_returns_server_name(self, client) -> None:
        response = await client.get("/mcp/info", headers=_AUTH_HEADER)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "kmflow"

    async def test_info_returns_version(self, client) -> None:
        response = await client.get("/mcp/info", headers=_AUTH_HEADER)
        data = response.json()
        assert "version" in data

    async def test_info_returns_tools_list(self, client) -> None:
        response = await client.get("/mcp/info", headers=_AUTH_HEADER)
        data = response.json()
        assert isinstance(data["tools"], list)
        assert len(data["tools"]) > 0

    async def test_info_no_auth_rejected(self, client) -> None:
        response = await client.get("/mcp/info")
        assert response.status_code == 401


# =============================================================================
# GET /mcp/tools
# =============================================================================


@pytest.mark.asyncio
class TestMCPListTools:
    """Tests for GET /mcp/tools."""

    async def test_list_tools_returns_list(self, client) -> None:
        response = await client.get("/mcp/tools", headers=_AUTH_HEADER)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_tools_includes_get_engagement(self, client) -> None:
        response = await client.get("/mcp/tools", headers=_AUTH_HEADER)
        names = [t["name"] for t in response.json()]
        assert "get_engagement" in names

    async def test_list_tools_includes_list_evidence(self, client) -> None:
        response = await client.get("/mcp/tools", headers=_AUTH_HEADER)
        names = [t["name"] for t in response.json()]
        assert "list_evidence" in names

    async def test_list_tools_includes_search_patterns(self, client) -> None:
        response = await client.get("/mcp/tools", headers=_AUTH_HEADER)
        names = [t["name"] for t in response.json()]
        assert "search_patterns" in names

    async def test_list_tools_no_auth_rejected(self, client) -> None:
        response = await client.get("/mcp/tools")
        assert response.status_code == 401


# =============================================================================
# POST /mcp/tools/call — tool dispatch
# =============================================================================


@pytest.mark.asyncio
class TestMCPToolCall:
    """Tests for POST /mcp/tools/call."""

    async def test_unknown_tool_returns_error(self, client) -> None:
        response = await client.post(
            "/mcp/tools/call",
            json={"request_id": "r1", "tool_name": "does_not_exist", "arguments": {}},
            headers=_AUTH_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Unknown tool" in data["error"]

    async def test_call_preserves_request_id(self, client) -> None:
        response = await client.post(
            "/mcp/tools/call",
            json={"request_id": "req-abc-123", "tool_name": "search_patterns", "arguments": {}},
            headers=_AUTH_HEADER,
        )
        data = response.json()
        assert data["request_id"] == "req-abc-123"

    async def test_call_search_patterns_success(self, client) -> None:
        """search_patterns doesn't need an engagement_id and queries PatternLibraryEntry."""
        response = await client.post(
            "/mcp/tools/call",
            json={"request_id": "r2", "tool_name": "search_patterns", "arguments": {}},
            headers=_AUTH_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "patterns" in data["result"]

    async def test_call_run_simulation_success(self, client) -> None:
        """run_simulation queues a simulation and returns status."""
        response = await client.post(
            "/mcp/tools/call",
            json={
                "request_id": "r3",
                "tool_name": "run_simulation",
                "arguments": {"scenario_name": "Test Scenario", "simulation_type": "what_if"},
            },
            headers=_AUTH_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["result"]["status"] == "simulation_queued"
        assert data["result"]["scenario_name"] == "Test Scenario"

    async def test_call_get_engagement_returns_result(self, client) -> None:
        """get_engagement returns a result dict (not an HTTP error)."""
        response = await client.post(
            "/mcp/tools/call",
            json={
                "request_id": "r4",
                "tool_name": "get_engagement",
                "arguments": {"engagement_id": "00000000-0000-0000-0000-000000000000"},
            },
            headers=_AUTH_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["result"] is not None

    async def test_call_list_evidence_returns_items_key(self, client) -> None:
        """list_evidence result always contains 'items'."""
        response = await client.post(
            "/mcp/tools/call",
            json={
                "request_id": "r5",
                "tool_name": "list_evidence",
                "arguments": {"engagement_id": "00000000-0000-0000-0000-000000000000"},
            },
            headers=_AUTH_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "items" in data["result"]

    async def test_call_get_gaps_returns_gaps_key(self, client) -> None:
        """get_gaps result contains 'gaps' list."""
        response = await client.post(
            "/mcp/tools/call",
            json={
                "request_id": "r6",
                "tool_name": "get_gaps",
                "arguments": {"engagement_id": "00000000-0000-0000-0000-000000000000"},
            },
            headers=_AUTH_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "gaps" in data["result"]

    async def test_call_get_deviations_returns_deviations_key(self, client) -> None:
        """get_deviations result contains 'deviations' list."""
        response = await client.post(
            "/mcp/tools/call",
            json={
                "request_id": "r7",
                "tool_name": "get_deviations",
                "arguments": {"engagement_id": "00000000-0000-0000-0000-000000000000"},
            },
            headers=_AUTH_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "deviations" in data["result"]

    async def test_call_get_monitoring_status_returns_active_jobs(self, client) -> None:
        """get_monitoring_status result contains 'active_jobs'."""
        response = await client.post(
            "/mcp/tools/call",
            json={
                "request_id": "r8",
                "tool_name": "get_monitoring_status",
                "arguments": {"engagement_id": "00000000-0000-0000-0000-000000000000"},
            },
            headers=_AUTH_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "active_jobs" in data["result"]
        assert "open_alerts" in data["result"]

    async def test_call_get_process_model_returns_result(self, client) -> None:
        """get_process_model returns a result dict on success."""
        response = await client.post(
            "/mcp/tools/call",
            json={
                "request_id": "r9",
                "tool_name": "get_process_model",
                "arguments": {"engagement_id": "00000000-0000-0000-0000-000000000000"},
            },
            headers=_AUTH_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["result"] is not None

    async def test_call_no_auth_rejected(self, client) -> None:
        response = await client.post(
            "/mcp/tools/call",
            json={"request_id": "r10", "tool_name": "search_patterns", "arguments": {}},
        )
        assert response.status_code == 401


# =============================================================================
# POST /mcp/tools/call/stream — SSE streaming
# =============================================================================


@pytest.mark.asyncio
class TestMCPToolCallStream:
    """Tests for POST /mcp/tools/call/stream."""

    async def test_stream_returns_event_stream_content_type(self, client) -> None:
        response = await client.post(
            "/mcp/tools/call/stream",
            json={"request_id": "s1", "tool_name": "run_simulation", "arguments": {}},
            headers=_AUTH_HEADER,
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    async def test_stream_contains_start_event(self, client) -> None:
        response = await client.post(
            "/mcp/tools/call/stream",
            json={"request_id": "s2", "tool_name": "search_patterns", "arguments": {}},
            headers=_AUTH_HEADER,
        )
        content = response.text
        # Parse the first SSE event
        first_line = next(line for line in content.splitlines() if line.startswith("data:"))
        event = json.loads(first_line[len("data: ") :].strip())
        assert event["type"] == "start"

    async def test_stream_contains_done_event(self, client) -> None:
        response = await client.post(
            "/mcp/tools/call/stream",
            json={"request_id": "s3", "tool_name": "search_patterns", "arguments": {}},
            headers=_AUTH_HEADER,
        )
        content = response.text
        data_lines = [line for line in content.splitlines() if line.startswith("data:")]
        last_event = json.loads(data_lines[-1][len("data: ") :].strip())
        assert last_event["type"] == "done"

    async def test_stream_no_auth_rejected(self, client) -> None:
        response = await client.post(
            "/mcp/tools/call/stream",
            json={"request_id": "s4", "tool_name": "search_patterns", "arguments": {}},
        )
        assert response.status_code == 401
