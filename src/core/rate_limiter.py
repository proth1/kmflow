"""Per-user Redis-backed rate limiter for copilot endpoint.

Uses a sliding window algorithm with Redis sorted sets to track
request timestamps per user.
"""

from __future__ import annotations

import logging
import time

from fastapi import Depends, HTTPException, Request, status

from src.core.config import get_settings
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)


async def copilot_rate_limit(
    request: Request,
    user=Depends(require_permission("copilot:query")),
):
    """FastAPI dependency that enforces per-user rate limiting on copilot.

    Uses Redis sorted sets with timestamps as scores for sliding window.
    Falls back to allowing the request if Redis is unavailable.

    Returns the authenticated user (passes through from require_permission).
    """
    settings = get_settings()
    max_requests = settings.copilot_rate_limit_per_user
    window_seconds = settings.copilot_rate_limit_window

    redis_client = getattr(request.app.state, "redis_client", None)
    if not redis_client:
        return user

    user_id = str(user.id)
    key = f"copilot_rate:{user_id}"
    now = time.time()
    window_start = now - window_seconds

    try:
        pipe = redis_client.pipeline()
        # Remove expired entries
        pipe.zremrangebyscore(key, 0, window_start)
        # Count remaining entries
        pipe.zcard(key)
        # Add current request
        pipe.zadd(key, {str(now): now})
        # Set TTL on the key
        pipe.expire(key, window_seconds + 1)
        results = await pipe.execute()

        request_count = results[1]

        if request_count >= max_requests:
            retry_after = int(window_seconds - (now - window_start))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Max {max_requests} copilot queries per {window_seconds}s.",
                headers={"Retry-After": str(max(retry_after, 1))},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Rate limiter Redis error (allowing request): %s", e)

    return user
