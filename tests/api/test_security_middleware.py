"""Tests for security middleware (src/api/middleware/security.py).

Covers:
- Request ID middleware
- Security headers middleware
- Rate limiting middleware
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

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
