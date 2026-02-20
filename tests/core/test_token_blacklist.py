"""Tests for token blacklist functions in src/core/auth.py.

Covers:
- is_token_blacklisted returns True for a blacklisted token
- is_token_blacklisted returns False for a clean token
- is_token_blacklisted fails closed (returns True) when Redis is unavailable
- blacklist_token calls setex with the correct key and TTL
- blacklist_token does not raise when Redis is unavailable
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.auth import blacklist_token, is_token_blacklisted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(redis_client: AsyncMock) -> MagicMock:
    """Build a minimal mock FastAPI Request with a redis_client on app.state."""
    request = MagicMock()
    request.app.state.redis_client = redis_client
    return request


# ---------------------------------------------------------------------------
# is_token_blacklisted
# ---------------------------------------------------------------------------


class TestIsTokenBlacklisted:
    """Tests for is_token_blacklisted()."""

    @pytest.mark.asyncio
    async def test_blacklisted_token_returns_true(self) -> None:
        """Redis returns a non-None value → token is blacklisted."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"1")
        request = _make_request(redis)

        result = await is_token_blacklisted(request, "some.jwt.token")

        assert result is True
        redis.get.assert_awaited_once_with("token:blacklist:some.jwt.token")

    @pytest.mark.asyncio
    async def test_non_blacklisted_token_returns_false(self) -> None:
        """Redis returns None → token is not blacklisted."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        request = _make_request(redis)

        result = await is_token_blacklisted(request, "clean.jwt.token")

        assert result is False
        redis.get.assert_awaited_once_with("token:blacklist:clean.jwt.token")

    @pytest.mark.asyncio
    async def test_redis_failure_fails_closed(self) -> None:
        """When Redis raises any exception, fail closed by returning True.

        This prevents a Redis outage from becoming an authentication bypass.
        """
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=ConnectionError("Redis unreachable"))
        request = _make_request(redis)

        result = await is_token_blacklisted(request, "any.jwt.token")

        assert result is True

    @pytest.mark.asyncio
    async def test_blacklist_key_format(self) -> None:
        """The Redis key must follow the 'token:blacklist:{token}' convention."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        request = _make_request(redis)

        token = "header.payload.signature"
        await is_token_blacklisted(request, token)

        expected_key = f"token:blacklist:{token}"
        redis.get.assert_awaited_once_with(expected_key)


# ---------------------------------------------------------------------------
# blacklist_token
# ---------------------------------------------------------------------------


class TestBlacklistToken:
    """Tests for blacklist_token()."""

    @pytest.mark.asyncio
    async def test_blacklist_token_sets_with_expiry(self) -> None:
        """blacklist_token stores the token key with the correct TTL via setex."""
        redis = AsyncMock()
        redis.setex = AsyncMock()
        request = _make_request(redis)

        token = "header.payload.signature"
        expires_in = 900

        await blacklist_token(request, token, expires_in=expires_in)

        redis.setex.assert_awaited_once_with(
            f"token:blacklist:{token}",
            expires_in,
            "1",
        )

    @pytest.mark.asyncio
    async def test_blacklist_token_default_ttl(self) -> None:
        """The default TTL for blacklist_token is 1800 seconds."""
        redis = AsyncMock()
        redis.setex = AsyncMock()
        request = _make_request(redis)

        await blacklist_token(request, "a.b.c")

        _key, ttl, _val = redis.setex.call_args.args
        assert ttl == 1800

    @pytest.mark.asyncio
    async def test_blacklist_token_does_not_raise_on_redis_failure(self) -> None:
        """When Redis is unavailable, blacklist_token logs a warning but does not raise."""
        redis = AsyncMock()
        redis.setex = AsyncMock(side_effect=ConnectionError("Redis unreachable"))
        request = _make_request(redis)

        # Must not propagate the exception
        await blacklist_token(request, "a.b.c")

    @pytest.mark.asyncio
    async def test_round_trip_blacklist_detection(self) -> None:
        """After blacklisting, the same token reads as blacklisted."""
        token = "round.trip.token"
        stored: dict[str, str] = {}

        async def fake_setex(key: str, ttl: int, value: str) -> None:  # noqa: ARG001
            stored[key] = value

        async def fake_get(key: str) -> bytes | None:
            return stored.get(key, None)  # type: ignore[return-value]

        redis = AsyncMock()
        redis.setex = fake_setex
        redis.get = fake_get
        request = _make_request(redis)

        # Not blacklisted yet
        assert await is_token_blacklisted(request, token) is False

        # Blacklist it
        await blacklist_token(request, token, expires_in=60)

        # Now it should be detected
        assert await is_token_blacklisted(request, token) is True
