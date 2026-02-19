"""Tests for the configuration module."""

from __future__ import annotations

import os
from unittest.mock import patch

from src.core.config import Settings, get_settings


class TestSettings:
    """Test suite for application Settings."""

    def test_default_values(self) -> None:
        """Settings should have sensible defaults."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(
                _env_file=None,  # type: ignore[call-arg]
            )
        assert settings.app_name == "KMFlow"
        assert settings.app_env == "development"
        assert settings.debug is True
        assert settings.postgres_port == 5432
        assert settings.redis_port == 6379

    def test_database_url_built_from_components(self) -> None:
        """database_url should be derived from components when not set."""
        settings = Settings(
            postgres_host="db-host",
            postgres_port=5433,
            postgres_db="testdb",
            postgres_user="testuser",
            postgres_password="testpass",
            database_url=None,
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.database_url == "postgresql+asyncpg://testuser:testpass@db-host:5433/testdb"

    def test_redis_url_built_from_components(self) -> None:
        """redis_url should be derived from host/port when not set."""
        settings = Settings(
            redis_host="cache-host",
            redis_port=6380,
            redis_url=None,
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.redis_url == "redis://cache-host:6380/0"

    def test_explicit_database_url_not_overwritten(self) -> None:
        """An explicit database_url should be preserved."""
        explicit_url = "postgresql+asyncpg://explicit@host/db"
        settings = Settings(
            database_url=explicit_url,
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.database_url == explicit_url

    def test_cors_origins_from_json_string(self) -> None:
        """CORS origins should parse from a JSON array string."""
        settings = Settings(
            cors_origins='["http://a.com","http://b.com"]',  # type: ignore[arg-type]
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.cors_origins == ["http://a.com", "http://b.com"]

    def test_cors_origins_from_comma_string(self) -> None:
        """CORS origins should parse from a comma-separated string."""
        settings = Settings(
            cors_origins="http://a.com, http://b.com",  # type: ignore[arg-type]
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.cors_origins == ["http://a.com", "http://b.com"]

    def test_cors_origins_from_list(self) -> None:
        """CORS origins should accept a list directly."""
        origins = ["http://a.com", "http://b.com"]
        settings = Settings(
            cors_origins=origins,
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.cors_origins == origins

    def test_get_settings_returns_settings(self) -> None:
        """get_settings should return a Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)
        assert settings.app_name == "KMFlow"

    def test_environment_variable_override(self) -> None:
        """Environment variables should override defaults."""
        with patch.dict(os.environ, {"APP_NAME": "TestApp", "POSTGRES_PORT": "9999"}):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.app_name == "TestApp"
        assert settings.postgres_port == 9999


class TestJwtVerificationKeys:
    """Test suite for jwt_verification_keys property."""

    def test_multi_key_parsing(self) -> None:
        """Comma-separated JWT_SECRET_KEYS should return multiple keys."""
        settings = Settings(
            jwt_secret_keys="key1,key2,key3",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.jwt_verification_keys == ["key1", "key2", "key3"]

    def test_multi_key_strips_whitespace(self) -> None:
        """Keys with whitespace should be trimmed."""
        settings = Settings(
            jwt_secret_keys=" key1 , key2 , key3 ",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.jwt_verification_keys == ["key1", "key2", "key3"]

    def test_single_key_fallback(self) -> None:
        """When jwt_secret_keys is empty, falls back to jwt_secret_key."""
        settings = Settings(
            jwt_secret_key="my-single-key",
            jwt_secret_keys="",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.jwt_verification_keys == ["my-single-key"]

    def test_empty_string_returns_fallback(self) -> None:
        """Empty jwt_secret_keys returns single jwt_secret_key."""
        settings = Settings(
            jwt_secret_key="fallback-key",
            jwt_secret_keys="",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.jwt_verification_keys == ["fallback-key"]

    def test_only_whitespace_keys_filtered(self) -> None:
        """Comma-separated empty/whitespace values should be filtered out."""
        settings = Settings(
            jwt_secret_key="fallback",
            jwt_secret_keys=", , ",
            _env_file=None,  # type: ignore[call-arg]
        )
        # All entries are whitespace-only, so after stripping+filtering -> empty -> fallback
        assert settings.jwt_verification_keys == ["fallback"]

    def test_first_key_is_signing_key(self) -> None:
        """First key in the list is the primary signing key."""
        settings = Settings(
            jwt_secret_keys="signing-key,old-key-1,old-key-2",
            _env_file=None,  # type: ignore[call-arg]
        )
        keys = settings.jwt_verification_keys
        assert keys[0] == "signing-key"
        assert len(keys) == 3
