"""Tests for MCP authentication and server endpoints."""

from __future__ import annotations

import pytest

from src.mcp.auth import generate_api_key, revoke_api_key, verify_api_key


class TestMCPAuth:
    """Test suite for MCP authentication functions."""

    def test_generate_api_key_returns_dict(self) -> None:
        """generate_api_key should return dict with key_id and api_key."""
        result = generate_api_key("test-client")
        assert "key_id" in result
        assert "api_key" in result

    def test_generate_api_key_id_starts_with_kmflow(self) -> None:
        """generate_api_key key_id should start with 'kmflow_'."""
        result = generate_api_key("test-client")
        assert result["key_id"].startswith("kmflow_")

    def test_generate_api_key_format(self) -> None:
        """generate_api_key api_key should contain key_id.secret format."""
        result = generate_api_key("test-client")
        api_key = result["api_key"]
        key_id = result["key_id"]
        assert api_key.startswith(key_id + ".")
        assert "." in api_key

    def test_verify_api_key_valid(self) -> None:
        """verify_api_key with valid key should return client info."""
        result = generate_api_key("test-client")
        api_key = result["api_key"]
        client_info = verify_api_key(api_key)
        assert client_info is not None
        assert client_info["client_name"] == "test-client"
        assert client_info["key_id"] == result["key_id"]

    def test_verify_api_key_invalid(self) -> None:
        """verify_api_key with invalid key should return None."""
        client_info = verify_api_key("invalid_key.invalid_secret")
        assert client_info is None

    def test_verify_api_key_without_dot(self) -> None:
        """verify_api_key with key without dot should return None."""
        client_info = verify_api_key("invalid_key_without_dot")
        assert client_info is None

    def test_verify_api_key_wrong_secret(self) -> None:
        """verify_api_key with wrong secret should return None."""
        result = generate_api_key("test-client")
        key_id = result["key_id"]
        wrong_key = f"{key_id}.wrong_secret"
        client_info = verify_api_key(wrong_key)
        assert client_info is None

    def test_revoke_api_key_makes_inactive(self) -> None:
        """revoke_api_key should make key inactive."""
        result = generate_api_key("test-client")
        key_id = result["key_id"]
        success = revoke_api_key(key_id)
        assert success is True

    def test_revoked_key_fails_verification(self) -> None:
        """Revoked key should fail verification."""
        result = generate_api_key("test-client")
        api_key = result["api_key"]
        key_id = result["key_id"]
        revoke_api_key(key_id)
        client_info = verify_api_key(api_key)
        assert client_info is None

    def test_revoke_unknown_key(self) -> None:
        """revoke_api_key with unknown key should return False."""
        success = revoke_api_key("unknown_key")
        assert success is False


@pytest.mark.asyncio
class TestMCPServerRoutes:
    """Test suite for MCP server routes via FastAPI test client."""

    async def test_get_mcp_info(self, client) -> None:
        """GET /mcp/info should return server info (200)."""
        response = await client.get("/mcp/info")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert data["name"] == "kmflow"
        assert "version" in data
        assert "tools" in data

    async def test_get_mcp_tools(self, client) -> None:
        """GET /mcp/tools should return tool list (200)."""
        response = await client.get("/mcp/tools")
        assert response.status_code == 200
        tools = response.json()
        assert isinstance(tools, list)
        assert len(tools) > 0

    async def test_post_tools_call_valid_tool(self, client) -> None:
        """POST /mcp/tools/call with valid tool should return result (200)."""
        # Generate API key
        key_result = generate_api_key("test-client")
        api_key = key_result["api_key"]

        # Call a tool (get_engagement with a UUID)
        response = await client.post(
            "/mcp/tools/call",
            json={
                "request_id": "test-001",
                "tool_name": "get_engagement",
                "arguments": {"engagement_id": "00000000-0000-0000-0000-000000000000"},
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        # May not find engagement, but call should succeed

    async def test_post_tools_call_invalid_tool(self, client) -> None:
        """POST /mcp/tools/call with invalid tool should return error."""
        key_result = generate_api_key("test-client")
        api_key = key_result["api_key"]

        response = await client.post(
            "/mcp/tools/call",
            json={
                "request_id": "test-002",
                "tool_name": "nonexistent_tool",
                "arguments": {},
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "error" in data
        assert "Unknown tool" in data["error"]

    async def test_post_tools_call_stream(self, client) -> None:
        """POST /mcp/tools/call/stream should return SSE response."""
        key_result = generate_api_key("test-client")
        api_key = key_result["api_key"]

        response = await client.post(
            "/mcp/tools/call/stream",
            json={
                "request_id": "test-003",
                "tool_name": "search_patterns",
                "arguments": {},
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        # StreamingResponse returns 200
        assert response.status_code == 200
        # Check content type
        assert "text/event-stream" in response.headers.get("content-type", "")
