"""Tests for the auth API routes (src/api/routes/auth.py).

Covers token endpoint, refresh, me, and logout.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.auth import create_access_token, create_refresh_token, get_current_user, hash_password
from src.core.config import Settings
from src.core.models import User, UserRole


@pytest.fixture(autouse=True)
def _restore_real_auth(test_app):
    """Remove the global get_current_user override so auth tests use real JWT flow."""
    test_app.dependency_overrides.pop(get_current_user, None)
    yield
    # Re-add if needed (though test_app is session-scoped per test)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    role: UserRole = UserRole.PROCESS_ANALYST,
    password: str = "testpassword123",
    **kwargs,  # noqa: ANN003
) -> User:
    """Create a test User ORM object with hashed password."""
    defaults = {
        "id": uuid.uuid4(),
        "email": "analyst@example.com",
        "name": "Test Analyst",
        "role": role,
        "is_active": True,
        "hashed_password": hash_password(password),
    }
    defaults.update(kwargs)
    return User(**defaults)


def _mock_scalar_result(value):  # noqa: ANN001, ANN202
    """Create a mock result that returns value from .scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _test_settings() -> Settings:
    """Create test settings."""
    return Settings(
        jwt_secret_key="test-secret-key-for-tests",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        jwt_refresh_token_expire_minutes=10080,
        auth_dev_mode=True,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/auth/token
# ---------------------------------------------------------------------------


class TestGetToken:
    """POST /api/v1/auth/token"""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return access and refresh tokens for valid credentials."""
        user = _make_user()
        mock_db_session.execute.return_value = _mock_scalar_result(user)

        response = await client.post(
            "/api/v1/auth/token",
            json={"email": "analyst@example.com", "password": "testpassword123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 401 for wrong password."""
        user = _make_user()
        mock_db_session.execute.return_value = _mock_scalar_result(user)

        response = await client.post(
            "/api/v1/auth/token",
            json={"email": "analyst@example.com", "password": "wrongpassword"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_user_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 401 for nonexistent user."""
        mock_db_session.execute.return_value = _mock_scalar_result(None)

        response = await client.post(
            "/api/v1/auth/token",
            json={"email": "nobody@example.com", "password": "whatever"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 401 for disabled user."""
        user = _make_user(is_active=False)
        mock_db_session.execute.return_value = _mock_scalar_result(user)

        response = await client.post(
            "/api/v1/auth/token",
            json={"email": "analyst@example.com", "password": "testpassword123"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_no_hashed_password(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 401 for user without password (OIDC-only)."""
        user = _make_user()
        user.hashed_password = None
        mock_db_session.execute.return_value = _mock_scalar_result(user)

        response = await client.post(
            "/api/v1/auth/token",
            json={"email": "analyst@example.com", "password": "whatever"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/auth/refresh
# ---------------------------------------------------------------------------


class TestRefreshToken:
    """POST /api/v1/auth/refresh"""

    @pytest.mark.asyncio
    async def test_refresh_success(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return new token pair for valid refresh token."""
        user = _make_user()
        settings = _test_settings()
        refresh = create_refresh_token({"sub": str(user.id)}, settings)

        mock_db_session.execute.return_value = _mock_scalar_result(user)

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_fails(self, client: AsyncClient) -> None:
        """Should reject access tokens used as refresh tokens."""
        settings = _test_settings()
        access = create_access_token({"sub": str(uuid.uuid4())}, settings)

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, client: AsyncClient) -> None:
        """Should return 401 for invalid refresh token."""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid.token.string"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/auth/me
# ---------------------------------------------------------------------------


class TestGetMe:
    """GET /api/v1/auth/me"""

    @pytest.mark.asyncio
    async def test_me_authenticated(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return current user info when authenticated."""
        user = _make_user()
        settings = _test_settings()
        token = create_access_token({"sub": str(user.id)}, settings)

        mock_db_session.execute.return_value = _mock_scalar_result(user)

        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "analyst@example.com"
        assert data["role"] == "process_analyst"

    @pytest.mark.asyncio
    async def test_me_unauthenticated(self, client: AsyncClient) -> None:
        """Should return 401 without authorization header."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/auth/logout
# ---------------------------------------------------------------------------


class TestLogout:
    """POST /api/v1/auth/logout"""

    @pytest.mark.asyncio
    async def test_logout_success(self, client: AsyncClient, mock_redis_client: AsyncMock) -> None:
        """Should return 200 with a confirmation message and blacklist the token.

        The logout endpoint was updated (Issue #156) to return 200 + JSON body
        instead of 204, so that it can also clear HttpOnly auth cookies via
        Set-Cookie response headers.
        """
        settings = _test_settings()
        token = create_access_token({"sub": str(uuid.uuid4())}, settings)

        response = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Logged out"

        # Verify Redis was called to blacklist
        mock_redis_client.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logout_unauthenticated(self, client: AsyncClient) -> None:
        """Should return 401 without authorization header."""
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 401
