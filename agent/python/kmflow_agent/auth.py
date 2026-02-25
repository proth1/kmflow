"""JWT authentication for agent-to-backend HTTP requests.

Manages a bearer token obtained during agent registration and injects
it into all outbound requests via a shared httpx.AsyncClient.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


def get_auth_token() -> str | None:
    """Read the agent JWT from environment or token file."""
    token = os.environ.get("KMFLOW_AGENT_TOKEN")
    if token:
        return token

    token_path = os.path.expanduser(
        "~/Library/Application Support/KMFlowAgent/.agent_token"
    )
    try:
        with open(token_path) as f:
            return f.read().strip()
    except OSError:
        return None


def create_http_client(token: str | None = None) -> httpx.AsyncClient:
    """Create a shared httpx.AsyncClient with auth headers."""
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.AsyncClient(headers=headers, timeout=30.0)
