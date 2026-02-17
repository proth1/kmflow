"""API key authentication for MCP server.

Provides simple API key verification for MCP tool calls.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from typing import Any

logger = logging.getLogger(__name__)

# In-memory store for API keys (would be DB-backed in production)
_api_keys: dict[str, dict[str, Any]] = {}


def generate_api_key(client_name: str) -> dict[str, str]:
    """Generate a new API key for an MCP client.

    Args:
        client_name: Name of the client application.

    Returns:
        Dict with key_id and api_key.
    """
    key_id = f"kmflow_{secrets.token_hex(8)}"
    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    _api_keys[key_id] = {
        "client_name": client_name,
        "key_hash": key_hash,
        "active": True,
    }

    return {"key_id": key_id, "api_key": f"{key_id}.{raw_key}"}


def verify_api_key(api_key: str) -> dict[str, Any] | None:
    """Verify an API key and return client info.

    Args:
        api_key: The full API key (key_id.secret).

    Returns:
        Client info dict if valid, None otherwise.
    """
    if "." not in api_key:
        return None

    key_id, raw_key = api_key.split(".", 1)
    key_info = _api_keys.get(key_id)
    if not key_info or not key_info.get("active"):
        return None

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    if not hmac.compare_digest(key_hash, key_info["key_hash"]):
        return None

    return {"key_id": key_id, "client_name": key_info["client_name"]}


def revoke_api_key(key_id: str) -> bool:
    """Revoke an API key."""
    if key_id in _api_keys:
        _api_keys[key_id]["active"] = False
        return True
    return False
