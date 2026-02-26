"""Tests for security middleware (src/api/middleware/security.py).

Covers:
- Request ID middleware
- Security headers middleware
- Rate limiting middleware (headers, pruning, X-Forwarded-For ignored)
"""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient

from src.api.middleware.security import RateLimitMiddleware, _RateLimitEntry

# ---------------------------------------------------------------------------
# Request ID
# ---------------------------------------------------------------------------


class TestRequestIDMiddleware:
    """Test the X-Request-ID middleware."""

    @pytest.mark.asyncio
    async def test_response_has_request_id(self, client: AsyncClient) -> None:
        """Every response should include an X-Request-ID header."""
        response = await client.get("/api/v1/health")
        assert "x-request-id" in response.headers

    @pytest.mark.asyncio
    async def test_client_provided_request_id_preserved(self, client: AsyncClient) -> None:
        """If client sends X-Request-ID, it should be echoed back."""
        response = await client.get(
            "/api/v1/health",
            headers={"X-Request-ID": "my-custom-id-123"},
        )
        assert response.headers.get("x-request-id") == "my-custom-id-123"

    @pytest.mark.asyncio
    async def test_generated_request_id_is_uuid(self, client: AsyncClient) -> None:
        """Auto-generated request IDs should look like UUIDs."""
        response = await client.get("/api/v1/health")
        request_id = response.headers.get("x-request-id", "")
        # UUID4 format: 8-4-4-4-12 hex chars
        parts = request_id.split("-")
        assert len(parts) == 5


# ---------------------------------------------------------------------------
# Security Headers
# ---------------------------------------------------------------------------


class TestSecurityHeadersMiddleware:
    """Test the security headers middleware."""

    @pytest.mark.asyncio
    async def test_x_content_type_options(self, client: AsyncClient) -> None:
        """Should set X-Content-Type-Options: nosniff."""
        response = await client.get("/api/v1/health")
        assert response.headers.get("x-content-type-options") == "nosniff"

    @pytest.mark.asyncio
    async def test_x_frame_options(self, client: AsyncClient) -> None:
        """Should set X-Frame-Options: DENY."""
        response = await client.get("/api/v1/health")
        assert response.headers.get("x-frame-options") == "DENY"

    @pytest.mark.asyncio
    async def test_x_xss_protection(self, client: AsyncClient) -> None:
        """Should set X-XSS-Protection."""
        response = await client.get("/api/v1/health")
        assert response.headers.get("x-xss-protection") == "1; mode=block"

    @pytest.mark.asyncio
    async def test_referrer_policy(self, client: AsyncClient) -> None:
        """Should set Referrer-Policy."""
        response = await client.get("/api/v1/health")
        assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_cache_control(self, client: AsyncClient) -> None:
        """Should set Cache-Control: no-store."""
        response = await client.get("/api/v1/health")
        assert response.headers.get("cache-control") == "no-store"

    @pytest.mark.asyncio
    async def test_api_version_matches_canonical_constant(self, client: AsyncClient) -> None:
        """X-API-Version header should match the canonical API_VERSION constant."""
        from src.api.version import API_VERSION

        response = await client.get("/api/v1/health")
        assert response.headers.get("x-api-version") == API_VERSION


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------


class TestRateLimitMiddleware:
    """Test the rate limiting middleware."""

    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self, client: AsyncClient) -> None:
        """Responses should include rate limit headers."""
        response = await client.get("/api/v1/health")
        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers

    @pytest.mark.asyncio
    async def test_rate_limit_remaining_decreases(self, client: AsyncClient) -> None:
        """Remaining count should decrease with each request."""
        r1 = await client.get("/api/v1/health")
        r2 = await client.get("/api/v1/health")

        remaining1 = int(r1.headers.get("x-ratelimit-remaining", "0"))
        remaining2 = int(r2.headers.get("x-ratelimit-remaining", "0"))
        assert remaining2 < remaining1

    @pytest.mark.asyncio
    async def test_x_forwarded_for_not_trusted(self, client: AsyncClient) -> None:
        """X-Forwarded-For should NOT be used to determine client IP.

        An attacker can spoof the header to bypass per-IP rate limits.
        The middleware should use only request.client.host.
        """
        # Send requests with a spoofed X-Forwarded-For header;
        # the rate limit should still apply based on the real IP
        for _ in range(3):
            await client.get(
                "/api/v1/health",
                headers={"X-Forwarded-For": f"10.0.0.{_}"},
            )
        # All requests came from the same real IP, so remaining should
        # reflect 3+ requests consumed, not be reset by the spoofed header
        r = await client.get(
            "/api/v1/health",
            headers={"X-Forwarded-For": "10.0.0.99"},
        )
        remaining = int(r.headers.get("x-ratelimit-remaining", "0"))
        limit = int(r.headers.get("x-ratelimit-limit", "100"))
        assert remaining < limit - 3


# ---------------------------------------------------------------------------
# Rate Limiter Pruning (unit tests)
# ---------------------------------------------------------------------------


class TestRateLimitPruning:
    """Expired entries are pruned to prevent unbounded memory growth."""

    def test_prune_stale_removes_expired_entries(self) -> None:
        """_prune_stale should remove entries whose window has expired."""
        middleware = RateLimitMiddleware(app=None, max_requests=10, window_seconds=60)  # type: ignore[arg-type]
        now = time.monotonic()

        # Add 100 stale entries (window_start is beyond the window)
        for i in range(100):
            middleware._clients[f"10.0.0.{i}"] = _RateLimitEntry(
                count=5, window_start=now - 120,
            )

        # Add 2 active entries
        middleware._clients["active-1"] = _RateLimitEntry(count=1, window_start=now - 10)
        middleware._clients["active-2"] = _RateLimitEntry(count=3, window_start=now - 5)

        middleware._prune_stale(now)

        # Only active entries remain
        assert len(middleware._clients) == 2
        assert "active-1" in middleware._clients
        assert "active-2" in middleware._clients

    def test_prune_stale_preserves_active_entries(self) -> None:
        """Active entries (within the window) should not be pruned."""
        middleware = RateLimitMiddleware(app=None, max_requests=10, window_seconds=60)  # type: ignore[arg-type]
        now = time.monotonic()

        middleware._clients["recent"] = _RateLimitEntry(count=2, window_start=now - 30)
        middleware._prune_stale(now)

        assert "recent" in middleware._clients
        assert middleware._clients["recent"].count == 2
