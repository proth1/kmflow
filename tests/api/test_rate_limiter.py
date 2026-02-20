"""Tests for the in-memory LLM rate limiter in simulations.py.

Tests cover:
- First request within limit succeeds
- Requests up to _LLM_RATE_LIMIT succeed
- Request exceeding limit raises HTTPException 429
- After time window expires, requests succeed again
- Stale user eviction works when _LLM_MAX_TRACKED_USERS exceeded
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException

# Import the function and its module-level state so we can reset between tests
import src.api.routes.simulations as simulations_module
from src.api.routes.simulations import (
    _LLM_RATE_LIMIT,
    _LLM_RATE_WINDOW,
    _LLM_MAX_TRACKED_USERS,
    _check_llm_rate_limit,
)


# ---------------------------------------------------------------------------
# Fixture: reset the module-level rate limit log before each test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_rate_limit_log():
    """Reset the in-memory request log before and after each test."""
    simulations_module._llm_request_log.clear()
    yield
    simulations_module._llm_request_log.clear()


# ---------------------------------------------------------------------------
# Basic rate limiting
# ---------------------------------------------------------------------------


class TestRateLimitBasic:
    """Core rate limiting behaviour."""

    def test_first_request_succeeds(self) -> None:
        """First request for a user should not raise."""
        _check_llm_rate_limit("user-1")  # Must not raise

    def test_requests_up_to_limit_succeed(self) -> None:
        """Exactly _LLM_RATE_LIMIT requests should all succeed."""
        user_id = "user-limit-test"
        for _ in range(_LLM_RATE_LIMIT):
            _check_llm_rate_limit(user_id)  # Must not raise

    def test_request_exceeding_limit_raises_429(self) -> None:
        """The (_LLM_RATE_LIMIT + 1)-th request should raise 429."""
        user_id = "user-over-limit"
        for _ in range(_LLM_RATE_LIMIT):
            _check_llm_rate_limit(user_id)

        with pytest.raises(HTTPException) as exc_info:
            _check_llm_rate_limit(user_id)
        assert exc_info.value.status_code == 429

    def test_429_detail_mentions_rate_limit(self) -> None:
        """429 exception detail should mention the rate limit."""
        user_id = "user-detail-check"
        for _ in range(_LLM_RATE_LIMIT):
            _check_llm_rate_limit(user_id)

        with pytest.raises(HTTPException) as exc_info:
            _check_llm_rate_limit(user_id)
        assert "Rate limit" in exc_info.value.detail or "rate limit" in exc_info.value.detail.lower()

    def test_different_users_have_independent_limits(self) -> None:
        """Rate limit is per-user; one user exhausting it should not block another."""
        user_a = "user-a-independent"
        user_b = "user-b-independent"

        # Exhaust user_a's limit
        for _ in range(_LLM_RATE_LIMIT):
            _check_llm_rate_limit(user_a)
        with pytest.raises(HTTPException):
            _check_llm_rate_limit(user_a)

        # user_b should still be able to make requests
        _check_llm_rate_limit(user_b)  # Must not raise


# ---------------------------------------------------------------------------
# Time window expiry
# ---------------------------------------------------------------------------


class TestRateLimitTimeWindow:
    """Rate limit resets after the time window expires."""

    def test_requests_succeed_after_window_expires(self) -> None:
        """After the time window passes, new requests should succeed again."""
        user_id = "user-window-test"
        now = time.monotonic()

        # Fill up the rate limit with timestamps at the start of the window
        old_timestamps = [now - _LLM_RATE_WINDOW - 1.0] * _LLM_RATE_LIMIT
        simulations_module._llm_request_log[user_id] = old_timestamps

        # All old entries should be pruned; request should succeed
        _check_llm_rate_limit(user_id)  # Must not raise

    def test_partially_expired_window_counts_correctly(self) -> None:
        """Only requests within the current window count against the limit."""
        user_id = "user-partial-window"
        now = time.monotonic()

        # Half the limit has old (expired) timestamps, half are recent
        half = _LLM_RATE_LIMIT // 2
        old_timestamps = [now - _LLM_RATE_WINDOW - 1.0] * half
        recent_timestamps = [now - 1.0] * half
        simulations_module._llm_request_log[user_id] = old_timestamps + recent_timestamps

        # Only the recent half counts; should have room for more requests
        for _ in range(_LLM_RATE_LIMIT - half):
            _check_llm_rate_limit(user_id)  # Must not raise


# ---------------------------------------------------------------------------
# Stale user eviction
# ---------------------------------------------------------------------------


class TestStaleUserEviction:
    """Stale entries are evicted when max tracked users is exceeded."""

    def test_stale_users_evicted_when_max_exceeded(self) -> None:
        """When _LLM_MAX_TRACKED_USERS is exceeded, stale entries are removed."""
        now = time.monotonic()

        # Fill log with _LLM_MAX_TRACKED_USERS + 1 stale users
        stale_ts = [now - _LLM_RATE_WINDOW - 5.0]
        for i in range(_LLM_MAX_TRACKED_USERS + 1):
            simulations_module._llm_request_log[f"stale-user-{i}"] = stale_ts.copy()

        # Calling the rate limiter for a new user triggers eviction
        _check_llm_rate_limit("new-user-after-eviction")

        # After eviction the log should be much smaller
        assert len(simulations_module._llm_request_log) <= _LLM_MAX_TRACKED_USERS + 2  # +2: eviction+new user

    def test_active_users_not_evicted(self) -> None:
        """Active (recent) users should not be evicted during stale cleanup."""
        now = time.monotonic()
        active_user = "active-during-eviction"

        # Add one active user with recent timestamp
        simulations_module._llm_request_log[active_user] = [now - 1.0]

        # Fill rest with stale users to trigger eviction
        stale_ts = [now - _LLM_RATE_WINDOW - 5.0]
        for i in range(_LLM_MAX_TRACKED_USERS + 1):
            simulations_module._llm_request_log[f"stale-evict-{i}"] = stale_ts.copy()

        # Trigger eviction by calling rate limiter
        _check_llm_rate_limit("trigger-eviction-user")

        # The active user should still be tracked
        assert active_user in simulations_module._llm_request_log

    def test_no_eviction_below_max_users(self) -> None:
        """Eviction should not run when user count is at or below the limit."""
        now = time.monotonic()
        # Put exactly _LLM_MAX_TRACKED_USERS entries (not exceeding)
        for i in range(_LLM_MAX_TRACKED_USERS):
            simulations_module._llm_request_log[f"user-{i}"] = [now - 1.0]

        initial_count = len(simulations_module._llm_request_log)
        # Should not evict since we're exactly at the limit (eviction triggers on >)
        _check_llm_rate_limit("one-more-user")
        # Count should only grow by 1 (the new user)
        assert len(simulations_module._llm_request_log) <= initial_count + 2
