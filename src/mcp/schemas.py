"""MCP request/response schemas.

Defines the data structures for MCP tool calls and responses.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MCPToolCall(BaseModel):
    """A tool call from an MCP client."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class MCPToolResult(BaseModel):
    """Result of a tool call."""

    request_id: str | None = None
    tool_name: str
    success: bool
    result: Any = None
    error: str | None = None


class MCPServerInfo(BaseModel):
    """MCP server metadata."""

    name: str = "kmflow"
    version: str = "0.1.0"
    description: str = "KMFlow Process Intelligence Platform"
    tools: list[dict[str, Any]] = []
