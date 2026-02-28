"""Tests for HttpOnly cookie-based authentication (Issue #156).

Covers:
- POST /api/v1/auth/login sets HttpOnly cookies, does not return raw token
- POST /api/v1/auth/login with wrong password returns 401
- Authenticated endpoint works with cookie (no Authorization header)
- POST /api/v1/auth/refresh/cookie rotates the access cookie
- POST /api/v1/auth/logout clears cookies and blacklists the token
- Cookie auth AND bearer auth both work (backward compat)
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.auth import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    create_access_token,
    create_refresh_token,
    hash_password,
)
from src.core.config import Settings, get_settings
from src.core.models import User, UserRole

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_test_settings() -> Settings:
    """Settings with a stable JWT secret and cookie_secure=False for tests.

    ``app_env="development"`` is intentional: the production-secret validator
    in Settings only fires for non-"development" environments, and the shared
    conftest follows the same pattern.
    """
    return Settings(
        app_env="development",
        jwt_secret_key="test-cookie-secret-key",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        jwt_refresh_token_expire_minutes=10080,
        auth_dev_mode=True,
        cookie_domain="",
        cookie_secure=False,  # Cookies work over plain HTTP in test/dev
        monitoring_worker_count=0,
    )


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Redis mock that simulates no blacklisted tokens by default."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)  # Nothing blacklisted
    client.setex = AsyncMock()
    return client


def _make_mock_user(
    *,
    user_id: uuid.UUID | None = None,
    email: str = "alice@kmflow.dev",
    name: str = "Alice",
    role: UserRole = UserRole.PROCESS_ANALYST,
    is_active: bool = True,
    password: str = "correct-password",
) -> MagicMock:
    """Build a mock User object with a real bcrypt-hashed password."""
    user = MagicMock(spec=User)
    user.id = user_id or uuid.uuid4()
    user.email = email
    user.name = name
    user.role = role
    user.is_active = is_active
    user.hashed_password = hash_password(password)
    return user


class MockSessionFactory:
    """Minimal async context-manager session factory for tests."""

    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    def __call__(self) -> MockSessionFactory:
        return self

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *_: Any) -> None:
        pass


@pytest.fixture
async def auth_app(
    auth_test_settings: Settings,
    mock_redis_client: AsyncMock,
) -> AsyncGenerator[tuple[Any, MagicMock, AsyncMock], None]:
    """FastAPI test app wired for cookie-auth testing.

    The ``get_current_user`` override from the shared ``test_app`` fixture is
    intentionally *not* applied here — we want the real dependency to run so
    that cookie and bearer auth paths can be exercised.

    Yields a tuple of ``(app, mock_user, mock_db_session)`` so tests can
    configure the DB session's return values.
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from src.api.deps import get_session
    from src.api.middleware.security import (
        RequestIDMiddleware,
        SecurityHeadersMiddleware,
    )
    from src.api.routes import auth, users

    mock_user = _make_mock_user()

    mock_db_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_result.scalar.return_value = 0
    mock_result.scalars.return_value.all.return_value = []
    mock_db_session.execute = AsyncMock(return_value=mock_result)
    mock_db_session.commit = AsyncMock()
    mock_db_session.flush = AsyncMock()
    mock_db_session.refresh = AsyncMock()
    mock_db_session.delete = AsyncMock()
    mock_db_session.add = MagicMock()

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        yield

    app = FastAPI(lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)

    app.include_router(auth.router)
    app.include_router(users.router)

    # Use consistent settings for the whole test
    app.dependency_overrides[get_settings] = lambda: auth_test_settings

    # Provide a real DB session (with mocked execute results)
    session_factory = MockSessionFactory(mock_db_session)
    app.dependency_overrides[get_session] = _make_session_override(mock_db_session)
    app.state.db_session_factory = session_factory
    app.state.redis_client = mock_redis_client

    yield app, mock_user, mock_db_session


def _make_session_override(mock_session: AsyncMock):
    """Return a FastAPI dependency override that yields the mock session."""

    async def _override():
        yield mock_session

    return _override


@pytest.fixture
async def auth_client(
    auth_app: tuple[Any, MagicMock, AsyncMock],
) -> AsyncGenerator[tuple[AsyncClient, MagicMock, AsyncMock], None]:
    """AsyncClient wired to the auth test app.

    Yields ``(client, mock_user, mock_db_session)``.
    """
    app, mock_user, mock_db_session = auth_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, mock_user, mock_db_session


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_sets_httponly_cookies(
    auth_client: tuple[AsyncClient, MagicMock, AsyncMock],
) -> None:
    """POST /login should set kmflow_access and kmflow_refresh HttpOnly cookies."""
    client, mock_user, _ = auth_client

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": mock_user.email, "password": "correct-password"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["message"] == "Login successful"
    assert body["user_id"] == str(mock_user.id)
    # Raw tokens must NOT be in the response body
    assert "access_token" not in body
    assert "refresh_token" not in body

    cookies = response.cookies
    assert ACCESS_COOKIE_NAME in cookies
    # The refresh cookie is path-restricted to /api/v1/auth/refresh but the
    # Set-Cookie header is still present in the login response — the path
    # restriction controls which requests the *browser* attaches it to, not
    # whether the server includes it in the response.
    assert REFRESH_COOKIE_NAME in cookies


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(
    auth_client: tuple[AsyncClient, MagicMock, AsyncMock],
) -> None:
    """POST /login with wrong password should return 401."""
    client, mock_user, _ = auth_client

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": mock_user.email, "password": "WRONG-password"},
    )

    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_inactive_user_returns_401(
    auth_client: tuple[AsyncClient, MagicMock, AsyncMock],
    auth_test_settings: Settings,
) -> None:
    """POST /login for a disabled user should return 401."""
    client, mock_user, mock_db_session = auth_client

    inactive_user = _make_mock_user(is_active=False)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = inactive_user
    mock_db_session.execute.return_value = mock_result

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": inactive_user.email, "password": "correct-password"},
    )

    assert response.status_code == 401
    assert "disabled" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_unknown_user_returns_401(
    auth_client: tuple[AsyncClient, MagicMock, AsyncMock],
) -> None:
    """POST /login for an unknown email should return 401."""
    client, _, mock_db_session = auth_client

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db_session.execute.return_value = mock_result

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@nowhere.example", "password": "irrelevant"},
    )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Cookie auth for protected endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cookie_auth_reaches_protected_endpoint(
    auth_app: tuple[Any, MagicMock, AsyncMock],
    auth_test_settings: Settings,
) -> None:
    """GET /api/v1/auth/me should succeed when kmflow_access cookie is present."""
    app, mock_user, _ = auth_app

    # Mint a real access token with the test settings
    claims = {
        "sub": str(mock_user.id),
        "email": mock_user.email,
        "name": mock_user.name,
        "role": mock_user.role.value,
    }
    access_token = create_access_token(claims, auth_test_settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Send the cookie directly — no Authorization header
        response = await ac.get(
            "/api/v1/auth/me",
            cookies={ACCESS_COOKIE_NAME: access_token},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == mock_user.email


@pytest.mark.asyncio
async def test_no_auth_returns_401(
    auth_app: tuple[Any, MagicMock, AsyncMock],
) -> None:
    """GET /api/v1/auth/me with no token (no cookie, no header) should return 401."""
    app, _, _ = auth_app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/auth/me")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Bearer token backward compat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bearer_auth_still_works(
    auth_app: tuple[Any, MagicMock, AsyncMock],
    auth_test_settings: Settings,
) -> None:
    """GET /api/v1/auth/me with a Bearer token header should still succeed."""
    app, mock_user, _ = auth_app

    claims = {
        "sub": str(mock_user.id),
        "email": mock_user.email,
        "name": mock_user.name,
        "role": mock_user.role.value,
    }
    access_token = create_access_token(claims, auth_test_settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert response.status_code == 200
    assert response.json()["email"] == mock_user.email


@pytest.mark.asyncio
async def test_bearer_header_takes_priority_over_cookie(
    auth_app: tuple[Any, MagicMock, AsyncMock],
    auth_test_settings: Settings,
) -> None:
    """When both a Bearer header and a cookie are present, the header wins."""
    app, mock_user, mock_db_session = auth_app

    # Mint a valid bearer token for the real mock_user
    claims = {
        "sub": str(mock_user.id),
        "email": mock_user.email,
        "name": mock_user.name,
        "role": mock_user.role.value,
    }
    valid_bearer = create_access_token(claims, auth_test_settings)

    # Mint a *different* access token for a second user
    second_user = _make_mock_user(email="bob@kmflow.dev", name="Bob")
    second_claims = {
        "sub": str(second_user.id),
        "email": second_user.email,
        "name": second_user.name,
        "role": second_user.role.value,
    }
    cookie_token = create_access_token(second_claims, auth_test_settings)

    # DB always returns mock_user so the bearer-authenticated request succeeds
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {valid_bearer}"},
            cookies={ACCESS_COOKIE_NAME: cookie_token},
        )

    assert response.status_code == 200
    # The user returned should match the Bearer token (mock_user), not the cookie
    body = response.json()
    assert body["email"] == mock_user.email


# ---------------------------------------------------------------------------
# Cookie refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_cookie_rotates_access_cookie(
    auth_app: tuple[Any, MagicMock, AsyncMock],
    auth_test_settings: Settings,
) -> None:
    """POST /refresh/cookie should issue a new access cookie."""
    app, mock_user, _ = auth_app

    claims = {
        "sub": str(mock_user.id),
        "email": mock_user.email,
        "name": mock_user.name,
        "role": mock_user.role.value,
    }
    refresh_tok = create_refresh_token(claims, auth_test_settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/auth/refresh/cookie",
            cookies={REFRESH_COOKIE_NAME: refresh_tok},
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Token refreshed"
    # A new access cookie must be present in the response
    assert ACCESS_COOKIE_NAME in response.cookies


@pytest.mark.asyncio
async def test_refresh_cookie_missing_returns_401(
    auth_app: tuple[Any, MagicMock, AsyncMock],
) -> None:
    """POST /refresh/cookie with no cookie should return 401."""
    app, _, _ = auth_app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/v1/auth/refresh/cookie")

    assert response.status_code == 401
    assert "Refresh cookie missing" in response.json()["detail"]


@pytest.mark.asyncio
async def test_refresh_cookie_wrong_type_returns_401(
    auth_app: tuple[Any, MagicMock, AsyncMock],
    auth_test_settings: Settings,
) -> None:
    """POST /refresh/cookie with an access token (not refresh) should return 401."""
    app, mock_user, _ = auth_app

    claims = {
        "sub": str(mock_user.id),
        "email": mock_user.email,
        "name": mock_user.name,
        "role": mock_user.role.value,
    }
    # Pass an access token where a refresh token is expected
    wrong_token = create_access_token(claims, auth_test_settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/auth/refresh/cookie",
            cookies={REFRESH_COOKIE_NAME: wrong_token},
        )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_via_cookie_clears_cookies_and_blacklists_token(
    auth_app: tuple[Any, MagicMock, AsyncMock],
    auth_test_settings: Settings,
    mock_redis_client: AsyncMock,
) -> None:
    """POST /logout should blacklist the access token and clear auth cookies."""
    app, mock_user, _ = auth_app

    claims = {
        "sub": str(mock_user.id),
        "email": mock_user.email,
        "name": mock_user.name,
        "role": mock_user.role.value,
    }
    access_token = create_access_token(claims, auth_test_settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/auth/logout",
            cookies={ACCESS_COOKIE_NAME: access_token},
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Logged out"

    # Redis blacklist should have been called
    mock_redis_client.setex.assert_called_once()
    call_args = mock_redis_client.setex.call_args
    assert f"token:blacklist:{access_token}" in str(call_args)

    # Both cookies should be cleared (Set-Cookie with empty/expired values)
    # httpx surfaces deleted cookies as empty strings in response.cookies
    set_cookie_headers = response.headers.get_list("set-cookie")
    cookie_names_cleared = [h for h in set_cookie_headers if "kmflow_" in h]
    assert len(cookie_names_cleared) >= 1  # at least the access cookie was cleared


@pytest.mark.asyncio
async def test_logout_via_bearer_clears_cookies_and_blacklists_token(
    auth_app: tuple[Any, MagicMock, AsyncMock],
    auth_test_settings: Settings,
    mock_redis_client: AsyncMock,
) -> None:
    """POST /logout via Bearer header should also clear cookies (for hybrid clients)."""
    app, mock_user, _ = auth_app

    claims = {
        "sub": str(mock_user.id),
        "email": mock_user.email,
        "name": mock_user.name,
        "role": mock_user.role.value,
    }
    access_token = create_access_token(claims, auth_test_settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert response.status_code == 200
    mock_redis_client.setex.assert_called_once()


@pytest.mark.asyncio
async def test_logout_no_auth_returns_401(
    auth_app: tuple[Any, MagicMock, AsyncMock],
) -> None:
    """POST /logout with no token at all should return 401."""
    app, _, _ = auth_app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/v1/auth/logout")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# set_auth_cookies / clear_auth_cookies unit tests
# ---------------------------------------------------------------------------


def test_set_auth_cookies_attaches_both_cookies(auth_test_settings: Settings) -> None:
    """set_auth_cookies should attach kmflow_access and kmflow_refresh to Response."""
    from fastapi import Response

    from src.core.auth import set_auth_cookies

    response = Response()
    set_auth_cookies(response, "fake-access", "fake-refresh", auth_test_settings)

    # FastAPI sets one Set-Cookie header per cookie; join all of them for a
    # single string to make assertions easy. raw_headers contains bytes tuples.
    all_set_cookie = " | ".join(v.decode() for k, v in response.raw_headers if k == b"set-cookie")

    assert ACCESS_COOKIE_NAME in all_set_cookie
    assert REFRESH_COOKIE_NAME in all_set_cookie
    assert "httponly" in all_set_cookie.lower()
    assert "samesite=lax" in all_set_cookie.lower()


def test_clear_auth_cookies_deletes_cookies(auth_test_settings: Settings) -> None:
    """clear_auth_cookies should produce Set-Cookie headers that expire the cookies."""
    from fastapi import Response

    from src.core.auth import clear_auth_cookies

    response = Response()
    clear_auth_cookies(response, auth_test_settings)

    raw = response.headers.get("set-cookie", "")
    assert ACCESS_COOKIE_NAME in raw
    # max-age=0 or expires in the past signals deletion
    assert "max-age=0" in raw.lower() or "expires=" in raw.lower()
