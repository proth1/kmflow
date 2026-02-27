"""Tests for the authentication module (src/core/auth.py).

Covers JWT creation, validation, token expiry, password hashing,
the get_current_user dependency, cookie auth, token blacklisting,
inactive user handling, and missing subject claims.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException

from src.core.auth import (
    ACCESS_COOKIE_NAME,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from src.core.config import Settings
from src.core.models import User, UserRole


@pytest.fixture
def settings() -> Settings:
    """Create test settings with known secret key."""
    return Settings(
        jwt_secret_key="test-secret-key-for-tests",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        jwt_refresh_token_expire_minutes=10080,
        auth_dev_mode=True,
    )


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    """Tests for bcrypt password hashing."""

    def test_hash_password_produces_hash(self) -> None:
        """hash_password should return a bcrypt hash string."""
        hashed = hash_password("mypassword123")
        assert hashed != "mypassword123"
        assert hashed.startswith("$2b$")

    def test_verify_password_correct(self) -> None:
        """verify_password should return True for correct password."""
        hashed = hash_password("correctpassword")
        assert verify_password("correctpassword", hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """verify_password should return False for wrong password."""
        hashed = hash_password("correctpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_hash_password_unique_salts(self) -> None:
        """Each hash should have a unique salt."""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # Different salts


# ---------------------------------------------------------------------------
# JWT creation
# ---------------------------------------------------------------------------


class TestCreateAccessToken:
    """Tests for access token creation."""

    def test_create_access_token_returns_string(self, settings: Settings) -> None:
        """Should return a non-empty JWT string."""
        token = create_access_token({"sub": "user-123"}, settings)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_includes_claims(self, settings: Settings) -> None:
        """Token should contain the provided claims."""
        claims = {"sub": "user-123", "email": "test@example.com", "role": "process_analyst"}
        token = create_access_token(claims, settings)
        decoded = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])

        assert decoded["sub"] == "user-123"
        assert decoded["email"] == "test@example.com"
        assert decoded["role"] == "process_analyst"
        assert decoded["type"] == "access"

    def test_create_access_token_has_expiry(self, settings: Settings) -> None:
        """Token should have an exp claim in the future."""
        token = create_access_token({"sub": "user-123"}, settings)
        decoded = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])

        exp = datetime.fromtimestamp(decoded["exp"], tz=UTC)
        assert exp > datetime.now(UTC)

    def test_create_access_token_custom_expiry(self, settings: Settings) -> None:
        """Custom expires_delta should override config."""
        token = create_access_token(
            {"sub": "user-123"},
            settings,
            expires_delta=timedelta(minutes=5),
        )
        decoded = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])

        exp = datetime.fromtimestamp(decoded["exp"], tz=UTC)
        # Should expire in ~5 minutes, not 30
        delta = exp - datetime.now(UTC)
        assert delta.total_seconds() < 310  # 5 min + small buffer


class TestCreateRefreshToken:
    """Tests for refresh token creation."""

    def test_create_refresh_token_type(self, settings: Settings) -> None:
        """Refresh token should have type='refresh'."""
        token = create_refresh_token({"sub": "user-123"}, settings)
        decoded = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert decoded["type"] == "refresh"

    def test_refresh_token_longer_expiry(self, settings: Settings) -> None:
        """Refresh token should have longer expiry than access token."""
        access = create_access_token({"sub": "user-123"}, settings)
        refresh = create_refresh_token({"sub": "user-123"}, settings)

        access_decoded = jwt.decode(access, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        refresh_decoded = jwt.decode(refresh, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])

        assert refresh_decoded["exp"] > access_decoded["exp"]


# ---------------------------------------------------------------------------
# JWT decoding
# ---------------------------------------------------------------------------


class TestDecodeToken:
    """Tests for token decoding and validation."""

    def test_decode_valid_token(self, settings: Settings) -> None:
        """Should successfully decode a valid token."""
        token = create_access_token({"sub": "user-123", "email": "test@example.com"}, settings)
        payload = decode_token(token, settings)
        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@example.com"

    def test_decode_invalid_token_raises(self, settings: Settings) -> None:
        """Should raise HTTPException for invalid token."""
        with pytest.raises(HTTPException) as exc_info:
            decode_token("invalid.token.string", settings)
        assert exc_info.value.status_code == 401

    def test_decode_wrong_secret_raises(self, settings: Settings) -> None:
        """Should raise HTTPException when decoded with wrong key."""
        token = create_access_token({"sub": "user-123"}, settings)
        wrong_settings = Settings(
            jwt_secret_key="wrong-secret",
            jwt_algorithm="HS256",
        )
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, wrong_settings)
        assert exc_info.value.status_code == 401

    def test_decode_expired_token_raises(self, settings: Settings) -> None:
        """Should raise HTTPException for an expired token."""
        token = create_access_token(
            {"sub": "user-123"},
            settings,
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, settings)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Cookie-based authentication (Issue #156)
# ---------------------------------------------------------------------------


class TestCookieAuth:
    """Tests for HttpOnly cookie authentication flow in get_current_user."""

    @pytest.fixture
    def auth_settings(self) -> Settings:
        """Settings for auth tests."""
        return Settings(
            jwt_secret_key="test-secret-key-for-tests",
            jwt_algorithm="HS256",
            jwt_access_token_expire_minutes=30,
            jwt_refresh_token_expire_minutes=10080,
            auth_dev_mode=True,
        )

    def _make_mock_user(self, user_id: uuid.UUID | None = None, is_active: bool = True) -> MagicMock:
        """Create a mock User object."""
        user = MagicMock(spec=User)
        user.id = user_id or uuid.uuid4()
        user.email = "test@kmflow.dev"
        user.name = "Test User"
        user.role = UserRole.PROCESS_ANALYST
        user.is_active = is_active
        return user

    def _make_mock_request(
        self,
        cookie_token: str | None = None,
        redis_blacklisted: bool = False,
    ) -> MagicMock:
        """Create a mock Request with optional cookie and redis state."""
        request = MagicMock()
        request.cookies = {}
        if cookie_token is not None:
            request.cookies[ACCESS_COOKIE_NAME] = cookie_token

        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=b"1" if redis_blacklisted else None)
        request.app.state.redis_client = redis_client

        return request

    @pytest.mark.asyncio
    async def test_cookie_auth_extracts_token(self, auth_settings: Settings) -> None:
        """get_current_user should fall back to cookie when no bearer header."""
        user_id = uuid.uuid4()
        token = create_access_token({"sub": str(user_id)}, auth_settings)

        request = self._make_mock_request(cookie_token=token)
        mock_user = self._make_mock_user(user_id=user_id)

        # Mock the session factory to return the user
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        request.app.state.db_session_factory = mock_factory

        user = await get_current_user(
            request=request,
            credentials=None,
            settings=auth_settings,
        )

        assert user.id == user_id

    @pytest.mark.asyncio
    async def test_no_token_no_cookie_raises_401(self, auth_settings: Settings) -> None:
        """Should raise 401 when neither bearer header nor cookie is present."""
        request = self._make_mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                request=request,
                credentials=None,
                settings=auth_settings,
            )
        assert exc_info.value.status_code == 401
        assert "Not authenticated" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Token blacklist checking
# ---------------------------------------------------------------------------


class TestTokenBlacklist:
    """Tests for token blacklist rejection in get_current_user."""

    @pytest.fixture
    def auth_settings(self) -> Settings:
        return Settings(
            jwt_secret_key="test-secret-key-for-tests",
            jwt_algorithm="HS256",
            auth_dev_mode=True,
        )

    @pytest.mark.asyncio
    async def test_blacklisted_token_raises_401(self, auth_settings: Settings) -> None:
        """A blacklisted token should be rejected with 401."""
        user_id = uuid.uuid4()
        token = create_access_token({"sub": str(user_id)}, auth_settings)

        request = MagicMock()
        request.cookies = {}

        # Redis returns a value -> token is blacklisted
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=b"1")
        request.app.state.redis_client = redis_client

        credentials = MagicMock()
        credentials.credentials = token

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                request=request,
                credentials=credentials,
                settings=auth_settings,
            )
        assert exc_info.value.status_code == 401
        assert "revoked" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Inactive user handling
# ---------------------------------------------------------------------------


class TestInactiveUser:
    """Tests for inactive user rejection in get_current_user."""

    @pytest.fixture
    def auth_settings(self) -> Settings:
        return Settings(
            jwt_secret_key="test-secret-key-for-tests",
            jwt_algorithm="HS256",
            auth_dev_mode=True,
        )

    @pytest.mark.asyncio
    async def test_inactive_user_raises_401(self, auth_settings: Settings) -> None:
        """An inactive user should be rejected with 401."""
        user_id = uuid.uuid4()
        token = create_access_token({"sub": str(user_id)}, auth_settings)

        inactive_user = MagicMock(spec=User)
        inactive_user.id = user_id
        inactive_user.is_active = False

        request = MagicMock()
        request.cookies = {}
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=None)
        request.app.state.redis_client = redis_client

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = inactive_user
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        request.app.state.db_session_factory = mock_factory

        credentials = MagicMock()
        credentials.credentials = token

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                request=request,
                credentials=credentials,
                settings=auth_settings,
            )
        assert exc_info.value.status_code == 401
        assert "disabled" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Missing subject claim
# ---------------------------------------------------------------------------


class TestMissingSubjectClaim:
    """Tests for missing 'sub' claim in JWT."""

    @pytest.fixture
    def auth_settings(self) -> Settings:
        return Settings(
            jwt_secret_key="test-secret-key-for-tests",
            jwt_algorithm="HS256",
            auth_dev_mode=True,
        )

    @pytest.mark.asyncio
    async def test_missing_sub_claim_raises_401(self, auth_settings: Settings) -> None:
        """A token without 'sub' claim should be rejected."""
        # Create a token without 'sub' — manually encode
        payload = {"type": "access", "exp": datetime.now(UTC) + timedelta(minutes=30)}
        token = jwt.encode(payload, auth_settings.jwt_secret_key, algorithm=auth_settings.jwt_algorithm)

        request = MagicMock()
        request.cookies = {}
        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=None)
        request.app.state.redis_client = redis_client

        credentials = MagicMock()
        credentials.credentials = token

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                request=request,
                credentials=credentials,
                settings=auth_settings,
            )
        assert exc_info.value.status_code == 401
        assert "subject" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Expired token via get_current_user
# ---------------------------------------------------------------------------


class TestExpiredTokenGetCurrentUser:
    """Tests for expired token handling through get_current_user."""

    @pytest.fixture
    def auth_settings(self) -> Settings:
        return Settings(
            jwt_secret_key="test-secret-key-for-tests",
            jwt_algorithm="HS256",
            auth_dev_mode=True,
        )

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self, auth_settings: Settings) -> None:
        """An expired access token should be rejected with 401."""
        token = create_access_token(
            {"sub": str(uuid.uuid4())},
            auth_settings,
            expires_delta=timedelta(seconds=-10),
        )

        request = MagicMock()
        request.cookies = {}

        credentials = MagicMock()
        credentials.credentials = token

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                request=request,
                credentials=credentials,
                settings=auth_settings,
            )
        assert exc_info.value.status_code == 401
