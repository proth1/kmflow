"""Unit tests for per-email login lockout helpers in src/api/routes/auth.py.

Covers:
- _check_email_lockout: allows when count is below threshold
- _check_email_lockout: blocks when count >= 10
- _record_failed_login: increments counter via pipeline
- _clear_login_lockout: deletes counter key
- Graceful degradation when Redis is unavailable (no exception raised)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request

from src.api.routes.auth import (
    _LOGIN_LOCKOUT_MAX_ATTEMPTS,
    _check_email_lockout,
    _clear_login_lockout,
    _get_redis_client,
    _record_failed_login,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(redis_client=None) -> Request:  # type: ignore[return]
    """Build a minimal mock Request whose app.state.redis_client is set."""
    state = MagicMock()
    state.redis_client = redis_client
    app = MagicMock()
    app.state = state
    request = MagicMock(spec=Request)
    request.app = app
    return request


def _make_request_no_redis() -> Request:
    """Build a mock Request with no Redis client on app state."""
    return _make_request(redis_client=None)


# ---------------------------------------------------------------------------
# _get_redis_client
# ---------------------------------------------------------------------------


class TestGetRedisClient:
    def test_returns_client_when_present(self) -> None:
        mock_redis = AsyncMock()
        request = _make_request(redis_client=mock_redis)
        assert _get_redis_client(request) is mock_redis

    def test_returns_none_when_no_app(self) -> None:
        request = MagicMock(spec=Request)
        request.app = None
        assert _get_redis_client(request) is None

    def test_returns_none_when_no_state(self) -> None:
        app = MagicMock()
        del app.state  # Make attribute access raise AttributeError
        request = MagicMock(spec=Request)
        request.app = app
        # getattr with default handles missing attribute gracefully
        assert _get_redis_client(request) is None

    def test_returns_none_when_redis_client_is_none(self) -> None:
        request = _make_request_no_redis()
        assert _get_redis_client(request) is None


# ---------------------------------------------------------------------------
# _check_email_lockout
# ---------------------------------------------------------------------------


class TestCheckEmailLockout:
    @pytest.mark.asyncio
    async def test_allows_when_count_below_threshold(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"3")
        request = _make_request(redis_client=redis)
        # Should not raise
        await _check_email_lockout("user@example.com", request)
        redis.get.assert_awaited_once_with("login_lockout:user@example.com")

    @pytest.mark.asyncio
    async def test_allows_when_count_is_none(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        request = _make_request(redis_client=redis)
        await _check_email_lockout("user@example.com", request)

    @pytest.mark.asyncio
    async def test_blocks_when_count_equals_threshold(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=str(_LOGIN_LOCKOUT_MAX_ATTEMPTS).encode())
        request = _make_request(redis_client=redis)
        with pytest.raises(HTTPException) as exc_info:
            await _check_email_lockout("locked@example.com", request)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_blocks_when_count_exceeds_threshold(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"25")
        request = _make_request(redis_client=redis)
        with pytest.raises(HTTPException) as exc_info:
            await _check_email_lockout("locked@example.com", request)
        assert exc_info.value.status_code == 429
        assert "Too many failed login attempts" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_graceful_when_redis_unavailable(self) -> None:
        request = _make_request_no_redis()
        # Should return without error when Redis is None
        await _check_email_lockout("user@example.com", request)

    @pytest.mark.asyncio
    async def test_graceful_when_redis_raises(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        request = _make_request(redis_client=redis)
        # Should not propagate non-HTTPException errors
        await _check_email_lockout("user@example.com", request)


# ---------------------------------------------------------------------------
# _record_failed_login
# ---------------------------------------------------------------------------


class TestRecordFailedLogin:
    @pytest.mark.asyncio
    async def test_increments_counter_via_pipeline(self) -> None:
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[1, True])
        redis = AsyncMock()
        redis.pipeline = MagicMock(return_value=pipe)
        request = _make_request(redis_client=redis)

        await _record_failed_login("user@example.com", request)

        pipe.incr.assert_called_once_with("login_lockout:user@example.com")
        pipe.expire.assert_called_once()
        pipe.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_graceful_when_redis_unavailable(self) -> None:
        request = _make_request_no_redis()
        await _record_failed_login("user@example.com", request)

    @pytest.mark.asyncio
    async def test_graceful_when_pipeline_raises(self) -> None:
        pipe = MagicMock()
        pipe.execute = AsyncMock(side_effect=ConnectionError("Redis down"))
        redis = AsyncMock()
        redis.pipeline = MagicMock(return_value=pipe)
        request = _make_request(redis_client=redis)
        # Should not raise
        await _record_failed_login("user@example.com", request)


# ---------------------------------------------------------------------------
# _clear_login_lockout
# ---------------------------------------------------------------------------


class TestClearLoginLockout:
    @pytest.mark.asyncio
    async def test_deletes_counter_key(self) -> None:
        redis = AsyncMock()
        redis.delete = AsyncMock(return_value=1)
        request = _make_request(redis_client=redis)

        await _clear_login_lockout("user@example.com", request)

        redis.delete.assert_awaited_once_with("login_lockout:user@example.com")

    @pytest.mark.asyncio
    async def test_graceful_when_redis_unavailable(self) -> None:
        request = _make_request_no_redis()
        await _clear_login_lockout("user@example.com", request)

    @pytest.mark.asyncio
    async def test_graceful_when_delete_raises(self) -> None:
        redis = AsyncMock()
        redis.delete = AsyncMock(side_effect=ConnectionError("Redis down"))
        request = _make_request(redis_client=redis)
        # contextlib.suppress(Exception) in implementation swallows errors
        await _clear_login_lockout("user@example.com", request)
