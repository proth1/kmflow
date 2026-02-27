"""API key authentication for MCP server.

Provides DB-backed API key verification for MCP tool calls.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import MCPAPIKey
from src.mcp.pii import mask_pii

logger = logging.getLogger(__name__)


async def generate_api_key(
    db: AsyncSession,
    user_id: uuid.UUID,
    client_name: str,
) -> dict[str, str]:
    """Generate a new API key for an MCP client.

    Args:
        db: Database session.
        user_id: UUID of the user creating the key.
        client_name: Name of the client application.

    Returns:
        Dict with key_id and api_key (raw key shown only once).
    """
    key_id = f"kmflow_{secrets.token_hex(8)}"
    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    api_key = MCPAPIKey(
        user_id=user_id,
        key_id=key_id,
        key_hash=key_hash,
        client_name=client_name,
        is_active=True,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    logger.info("Generated API key %s for user %s, client %s", key_id, user_id, mask_pii(client_name))
    return {"key_id": key_id, "api_key": f"{key_id}.{raw_key}"}


async def validate_api_key(db: AsyncSession, api_key: str) -> dict[str, Any] | None:
    """Validate an API key and return client info.

    Args:
        db: Database session.
        api_key: The full API key (key_id.secret).

    Returns:
        Dict with key_id, client_name, user_id if valid, None otherwise.
    """
    if "." not in api_key:
        logger.warning("API key missing '.' separator")
        return None

    key_id, raw_key = api_key.split(".", 1)

    # Query the database for this key_id
    stmt = select(MCPAPIKey).where(
        MCPAPIKey.key_id == key_id,
        MCPAPIKey.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    key_record = result.scalar_one_or_none()

    if not key_record:
        logger.warning("API key %s not found or inactive", key_id)
        return None

    # Hash the incoming key and compare with stored hash
    incoming_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    if not hmac.compare_digest(incoming_hash, key_record.key_hash):
        logger.warning("API key %s hash mismatch", key_id)
        return None

    # Update last_used_at timestamp
    key_record.last_used_at = datetime.now(UTC)
    await db.commit()

    logger.info("Validated API key %s for user %s", key_id, mask_pii(str(key_record.user_id)))
    return {
        "key_id": key_id,
        "client_name": key_record.client_name,
        "user_id": str(key_record.user_id),
    }


async def revoke_api_key(db: AsyncSession, key_id: str) -> bool:
    """Revoke an API key by setting is_active=False.

    Args:
        db: Database session.
        key_id: The key_id to revoke.

    Returns:
        True if key was found and revoked, False otherwise.
    """
    stmt = select(MCPAPIKey).where(MCPAPIKey.key_id == key_id)
    result = await db.execute(stmt)
    key_record = result.scalar_one_or_none()

    if not key_record:
        logger.warning("API key %s not found for revocation", key_id)
        return False

    key_record.is_active = False
    await db.commit()

    logger.info("Revoked API key %s", key_id)
    return True


async def list_api_keys(
    db: AsyncSession,
    user_id: uuid.UUID,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    """List API keys for a user.

    Args:
        db: Database session.
        user_id: UUID of the user.
        include_inactive: If True, include revoked keys. Default False.

    Returns:
        List of dicts with key_id, client_name, is_active, created_at, last_used_at.
    """
    stmt = select(MCPAPIKey).where(MCPAPIKey.user_id == user_id)
    if not include_inactive:
        stmt = stmt.where(MCPAPIKey.is_active == True)  # noqa: E712

    stmt = stmt.order_by(MCPAPIKey.created_at.desc())

    result = await db.execute(stmt)
    keys = result.scalars().all()

    return [
        {
            "key_id": key.key_id,
            "client_name": key.client_name,
            "is_active": key.is_active,
            "created_at": key.created_at.isoformat(),
            "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        }
        for key in keys
    ]
