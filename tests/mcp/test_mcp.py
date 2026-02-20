"""Tests for MCP authentication and server endpoints."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.mcp.auth import generate_api_key, revoke_api_key, validate_api_key, verify_api_key


class TestMCPAuthSync:
    """Test suite for synchronous MCP verify_api_key (backward compat)."""

    def test_verify_api_key_valid_format(self) -> None:
        """verify_api_key with kmflow_ prefix should return client info."""
        client_info = verify_api_key("kmflow_abc123.some_secret")
        assert client_info is not None
        assert client_info["key_id"] == "kmflow_abc123"

    def test_verify_api_key_invalid_prefix(self) -> None:
        """verify_api_key without kmflow_ prefix should return None."""
        client_info = verify_api_key("notkmflow_abc.secret")
        assert client_info is None

    def test_verify_api_key_without_dot(self) -> None:
        """verify_api_key with key without dot should return None."""
        client_info = verify_api_key("invalid_key_without_dot")
        assert client_info is None


@pytest.mark.asyncio
class TestMCPAuthAsync:
    """Test suite for async DB-backed MCP auth functions."""

    async def test_generate_api_key_returns_dict(self) -> None:
        """generate_api_key should return dict with key_id and api_key."""
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        result = await generate_api_key(db, uuid.uuid4(), "test-client")
        assert "key_id" in result
        assert "api_key" in result

    async def test_generate_api_key_id_starts_with_kmflow(self) -> None:
        """generate_api_key key_id should start with 'kmflow_'."""
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        result = await generate_api_key(db, uuid.uuid4(), "test-client")
        assert result["key_id"].startswith("kmflow_")

    async def test_generate_api_key_format(self) -> None:
        """generate_api_key api_key should contain key_id.secret format."""
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        result = await generate_api_key(db, uuid.uuid4(), "test-client")
        api_key = result["api_key"]
        key_id = result["key_id"]
        assert api_key.startswith(key_id + ".")
        assert "." in api_key

    async def test_validate_api_key_not_found(self) -> None:
        """validate_api_key with unknown key should return None."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        result = await validate_api_key(db, "kmflow_unknown.secret")
        assert result is None

    async def test_validate_api_key_without_dot(self) -> None:
        """validate_api_key with key without dot should return None."""
        db = AsyncMock()
        result = await validate_api_key(db, "no_dot_separator")
        assert result is None

    async def test_revoke_api_key_not_found(self) -> None:
        """revoke_api_key with unknown key should return False."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        result = await revoke_api_key(db, "unknown_key")
        assert result is False


@pytest.mark.asyncio
class TestMCPServerRoutes:
    """Test suite for MCP server routes via FastAPI test client."""

    @pytest.fixture(autouse=True)
    def _setup_mcp_key(self, test_app: Any, mock_db_session: AsyncMock) -> None:
        """Configure mock DB to return a valid MCPAPIKey for test bearer tokens."""
        mock_key = MagicMock()
        mock_key.key_id = "kmflow_testkey"
        mock_key.key_hash = hashlib.sha256(b"secretvalue").hexdigest()
        mock_key.is_active = True
        mock_key.user_id = uuid.uuid4()
        mock_key.client_name = "test-client"
        mock_key.expires_at = None

        # Make execute return a result that finds this key
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_key
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

    async def test_get_mcp_info_no_auth(self, client) -> None:
        """GET /mcp/info without auth should return 401."""
        response = await client.get("/mcp/info")
        assert response.status_code == 401

    async def test_get_mcp_tools_no_auth(self, client) -> None:
        """GET /mcp/tools without auth should return 401."""
        response = await client.get("/mcp/tools")
        assert response.status_code == 401

    async def test_post_tools_call_no_auth(self, client) -> None:
        """POST /mcp/tools/call without auth should return 401."""
        response = await client.post(
            "/mcp/tools/call",
            json={
                "request_id": "test-001",
                "tool_name": "get_engagement",
                "arguments": {"engagement_id": "00000000-0000-0000-0000-000000000000"},
            },
        )
        assert response.status_code == 401

    async def test_post_tools_call_with_valid_key(self, client) -> None:
        """POST /mcp/tools/call with valid format key should succeed."""
        response = await client.post(
            "/mcp/tools/call",
            json={
                "request_id": "test-001",
                "tool_name": "get_engagement",
                "arguments": {"engagement_id": "00000000-0000-0000-0000-000000000000"},
            },
            headers={"Authorization": "Bearer kmflow_testkey.secretvalue"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "success" in data

    async def test_post_tools_call_invalid_tool(self, client) -> None:
        """POST /mcp/tools/call with invalid tool should return error."""
        response = await client.post(
            "/mcp/tools/call",
            json={
                "request_id": "test-002",
                "tool_name": "nonexistent_tool",
                "arguments": {},
            },
            headers={"Authorization": "Bearer kmflow_testkey.secretvalue"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "error" in data
        assert "Unknown tool" in data["error"]

    async def test_post_tools_call_stream(self, client) -> None:
        """POST /mcp/tools/call/stream should return SSE response."""
        response = await client.post(
            "/mcp/tools/call/stream",
            json={
                "request_id": "test-003",
                "tool_name": "search_patterns",
                "arguments": {},
            },
            headers={"Authorization": "Bearer kmflow_testkey.secretvalue"},
        )
        # StreamingResponse returns 200
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
