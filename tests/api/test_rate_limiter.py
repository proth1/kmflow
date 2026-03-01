"""Tests for the Redis-backed LLM rate limiter in simulations.py.

Tests cover:
- First request within limit succeeds (Redis returns count 0)
- Requests at the limit boundary succeed (Redis returns count < _LLM_RATE_LIMIT)
- Request exceeding limit raises HTTPException 429 (Redis returns count >= _LLM_RATE_LIMIT)
- Redis unavailability falls back to allowing the request
- Redis errors fall back to allowing the request
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request

from src.api.routes.simulations import (
    _LLM_RATE_LIMIT,
    _LLM_RATE_WINDOW,
    _check_llm_rate_limit,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(redis_client: object | None) -> Request:
    """Build a mock FastAPI Request whose app.state.redis_client is set."""
    app = MagicMock()
    app.state.redis_client = redis_client
    request = MagicMock(spec=Request)
    request.app = app
    return request


def _make_redis(zcard_result: int) -> MagicMock:
    """Return a mock Redis client whose pipeline returns zcard_result."""
    pipe = AsyncMock()
    # pipe.execute() returns [zremrangebyscore_result, zcard_result, zadd_result, expire_result]
    pipe.execute = AsyncMock(return_value=[0, zcard_result, 1, True])
    # pipeline() is a sync call that returns the pipe mock
    redis_client = MagicMock()
    redis_client.pipeline = MagicMock(return_value=pipe)
    return redis_client


# ---------------------------------------------------------------------------
# Basic rate limiting
# ---------------------------------------------------------------------------


class TestRateLimitBasic:
    """Core rate limiting behaviour via Redis pipeline."""

    @pytest.mark.asyncio
    async def test_first_request_succeeds(self) -> None:
        """First request (count = 0) should not raise."""
        redis = _make_redis(zcard_result=0)
        request = _make_request(redis)
        await _check_llm_rate_limit(request, "user-1")  # Must not raise

    @pytest.mark.asyncio
    async def test_request_under_limit_succeeds(self) -> None:
        """A request where the current count is below _LLM_RATE_LIMIT should not raise."""
        redis = _make_redis(zcard_result=_LLM_RATE_LIMIT - 1)
        request = _make_request(redis)
        await _check_llm_rate_limit(request, "user-under-limit")  # Must not raise

    @pytest.mark.asyncio
    async def test_request_at_limit_raises_429(self) -> None:
        """When the current window count equals _LLM_RATE_LIMIT, the request is rejected."""
        redis = _make_redis(zcard_result=_LLM_RATE_LIMIT)
        request = _make_request(redis)
        with pytest.raises(HTTPException) as exc_info:
            await _check_llm_rate_limit(request, "user-at-limit")
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_429_detail_mentions_rate_limit(self) -> None:
        """429 exception detail should mention the rate limit."""
        redis = _make_redis(zcard_result=_LLM_RATE_LIMIT)
        request = _make_request(redis)
        with pytest.raises(HTTPException) as exc_info:
            await _check_llm_rate_limit(request, "user-detail-check")
        detail = exc_info.value.detail.lower()
        assert "rate limit" in detail

    @pytest.mark.asyncio
    async def test_retry_after_header_set(self) -> None:
        """429 response should include Retry-After header."""
        redis = _make_redis(zcard_result=_LLM_RATE_LIMIT)
        request = _make_request(redis)
        with pytest.raises(HTTPException) as exc_info:
            await _check_llm_rate_limit(request, "user-retry-after")
        assert "Retry-After" in exc_info.value.headers


# ---------------------------------------------------------------------------
# Redis unavailability / error handling
# ---------------------------------------------------------------------------


class TestRateLimitFallback:
    """Rate limiter degrades gracefully when Redis is unavailable."""

    @pytest.mark.asyncio
    async def test_no_redis_allows_request(self) -> None:
        """When redis_client is None, the request should be allowed (fail-open)."""
        request = _make_request(redis_client=None)
        await _check_llm_rate_limit(request, "user-no-redis")  # Must not raise

    @pytest.mark.asyncio
    async def test_redis_error_allows_request(self) -> None:
        """When the Redis pipeline raises RedisError, the request is allowed."""
        import redis.asyncio as aioredis

        pipe = AsyncMock()
        pipe.execute = AsyncMock(side_effect=aioredis.RedisError("connection refused"))
        redis_client = MagicMock()
        redis_client.pipeline = MagicMock(return_value=pipe)
        request = _make_request(redis_client)

        await _check_llm_rate_limit(request, "user-redis-error")  # Must not raise


# ---------------------------------------------------------------------------
# Rate limit constants sanity check
# ---------------------------------------------------------------------------


class TestRateLimitConstants:
    """Validate the exported constants are sane."""

    def test_rate_limit_is_positive(self) -> None:
        assert _LLM_RATE_LIMIT > 0

    def test_rate_window_is_positive(self) -> None:
        assert _LLM_RATE_WINDOW > 0
