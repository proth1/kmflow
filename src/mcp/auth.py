"""API key authentication for MCP server.

Provides DB-backed API key verification for MCP tool calls.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as _aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import MCPAPIKey
from src.mcp.pii import mask_pii

logger = logging.getLogger(__name__)

_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_WINDOW_SECONDS = 300  # 5 minutes
_MCP_RATE_LIMIT_REQUESTS = 100
_MCP_RATE_LIMIT_WINDOW = 60  # seconds


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


async def check_mcp_rate_limit(
    redis_client: Any,
    api_key: str,
    limit: int = _MCP_RATE_LIMIT_REQUESTS,
    window: int = _MCP_RATE_LIMIT_WINDOW,
) -> bool:
    """Check per-API-key request rate limit using Redis sliding window.

    Args:
        redis_client: An async Redis client (from app.state.redis_client).
        api_key: The API key identifier to rate-limit.
        limit: Maximum requests allowed per window.
        window: Window size in seconds.

    Returns:
        True if the request is within the limit, False if rate limit exceeded.
        Returns True (allow) if Redis is unavailable — rate limiting is
        best-effort and must not block authenticated requests.
    """
    key = f"mcp_ratelimit:{api_key}"
    try:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, window)
        if count > limit:
            logger.warning("MCP rate limit exceeded for key %s (%d/%d)", api_key, count, limit)
            return False
        return True
    except (ConnectionError, OSError, _aioredis.RedisError) as exc:
        logger.warning("Redis unavailable for MCP rate limit check — allowing request: %s", exc)
        return True


async def validate_api_key(
    db: AsyncSession,
    api_key: str,
    redis_client: Any | None = None,
) -> dict[str, Any] | None:
    """Validate an API key and return client info.

    Args:
        db: Database session.
        api_key: The full API key (key_id.secret).
        redis_client: Optional Redis client for rate limiting failed attempts.
            When provided, lockout state is stored in Redis (multi-worker safe).
            When absent, failed-attempt tracking is skipped.

    Returns:
        Dict with key_id, client_name, user_id if valid, None otherwise.
    """
    if "." not in api_key:
        logger.warning("API key missing '.' separator")
        return None

    key_id, raw_key = api_key.split(".", 1)

    # Per-key-id lockout for failed validation attempts (Redis-backed)
    if redis_client is not None:
        lockout_key = f"mcp_auth_failures:{key_id}"
        try:
            fail_count_raw = await redis_client.get(lockout_key)
            if fail_count_raw is not None and int(fail_count_raw) >= _MAX_FAILED_ATTEMPTS:
                logger.warning("API key %s locked out after repeated failed attempts", key_id)
                return None
        except (ConnectionError, OSError, _aioredis.RedisError) as exc:
            logger.warning("Redis unavailable for MCP auth lockout check — skipping: %s", exc)

    # Query the database for this key_id
    stmt = select(MCPAPIKey).where(
        MCPAPIKey.key_id == key_id,
        MCPAPIKey.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    key_record = result.scalar_one_or_none()

    if not key_record:
        logger.warning("API key %s not found or inactive", key_id)
        await _record_failed_attempt_redis(redis_client, key_id)
        return None

    # Hash the incoming key and compare with stored hash
    incoming_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    if not hmac.compare_digest(incoming_hash, key_record.key_hash):
        logger.warning("API key %s hash mismatch", key_id)
        await _record_failed_attempt_redis(redis_client, key_id)
        return None

    # Successful validation — clear failure counter
    if redis_client is not None:
        with contextlib.suppress(ConnectionError, OSError, _aioredis.RedisError):
            await redis_client.delete(f"mcp_auth_failures:{key_id}")

    # Update last_used_at timestamp
    key_record.last_used_at = datetime.now(UTC)
    await db.commit()

    logger.info("Validated API key %s for user %s", key_id, mask_pii(str(key_record.user_id)))
    return {
        "key_id": key_id,
        "client_name": key_record.client_name,
        "user_id": str(key_record.user_id),
    }


async def _record_failed_attempt_redis(redis_client: Any | None, key_id: str) -> None:
    """Increment the Redis-backed failed-attempt counter for a key."""
    if redis_client is None:
        return
    lockout_key = f"mcp_auth_failures:{key_id}"
    try:
        count = await redis_client.incr(lockout_key)
        if count == 1:
            await redis_client.expire(lockout_key, _LOCKOUT_WINDOW_SECONDS)
    except (ConnectionError, OSError, _aioredis.RedisError) as exc:
        logger.warning("Redis unavailable for MCP auth failure recording: %s", exc)


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
