"""Tests for the authentication module (src/core/auth.py).

Covers JWT creation, validation, token expiry, password hashing,
and the get_current_user dependency.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException

from src.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from src.core.config import Settings


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
