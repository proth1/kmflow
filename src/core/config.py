"""Application configuration using Pydantic Settings v2.

Loads configuration from environment variables with .env file support.
All settings are validated at startup and available as typed attributes.
"""

from __future__ import annotations

import functools
import json
from typing import Any

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """KMFlow application settings.

    Configuration is loaded from environment variables.
    A .env file in the project root is also read if present.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────
    app_name: str = "KMFlow"
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # ── PostgreSQL ───────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "kmflow"
    postgres_user: str = "kmflow"
    postgres_password: str = "kmflow_dev_password"
    database_url: str | None = None

    # ── Neo4j ────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j_dev_password"

    # ── Redis ────────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_url: str | None = None

    # ── Backend ──────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"  # noqa: S104 - intentional for container deployments  # nosec B104
    backend_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]

    # ── Security / Auth ───────────────────────────────────────────
    jwt_secret_key: str = "dev-secret-key-change-in-production"
    jwt_secret_keys: str = ""  # Comma-separated list for key rotation
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_minutes: int = 10080  # 7 days
    auth_dev_mode: bool = True  # Allow local dev tokens
    encryption_key: str = "dev-encryption-key-change-in-production"

    # ── RAG Copilot (Phase 4) ─────────────────────────────────────
    copilot_model: str = "claude-sonnet-4-5-20250929"
    copilot_max_context_tokens: int = 4000
    copilot_max_response_tokens: int = 2000

    # ── WebSocket Limits (Phase 4) ────────────────────────────────
    ws_max_connections_per_engagement: int = 10

    # ── Rate Limiting ─────────────────────────────────────────────
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # ── Copilot Rate Limiting (Phase 5) ─────────────────────────
    copilot_rate_limit_per_user: int = 10
    copilot_rate_limit_window: int = 60  # seconds

    # ── Data Retention (Phase 5) ──────────────────────────────
    retention_cleanup_enabled: bool = False

    # ── Encryption Key Rotation (Phase 5) ──────────────────────
    encryption_key_previous: str = ""  # Previous key for rotation

    # ── Storage Backend (Phase B: Data Layer Evolution) ──────────
    storage_backend: str = "local"  # "local" | "delta" | "databricks"
    evidence_store_path: str = "evidence_store"
    datalake_path: str = "datalake"

    # ── Databricks (Phase F: Databricks Preparation) ─────────────
    databricks_host: str = ""
    databricks_token: SecretStr = SecretStr("")
    databricks_catalog: str = "kmflow"
    databricks_schema: str = "evidence"
    databricks_volume: str = "raw_evidence"

    # ── Embeddings ───────────────────────────────────────────────
    embedding_model: str = "all-mpnet-base-v2"
    embedding_dimension: int = 768

    # ── Monitoring (Phase 3) ─────────────────────────────────────
    monitoring_worker_count: int = 2
    monitoring_stream_max_len: int = 10000
    monitoring_default_interval: str = "0 0 * * *"

    # ── WebSocket (Phase 3) ──────────────────────────────────────
    ws_heartbeat_interval: int = 30
    ws_heartbeat_timeout: int = 10

    # ── MCP Server (Phase 3) ─────────────────────────────────────
    mcp_enabled: bool = True
    mcp_rate_limit: int = 1000

    # ── Simulation (Phase 3) ─────────────────────────────────────
    simulation_max_concurrent: int = 3
    simulation_timeout_seconds: int = 300

    # ── Pattern Library (Phase 3) ────────────────────────────────
    pattern_anonymization_enabled: bool = True

    @property
    def jwt_verification_keys(self) -> list[str]:
        """Return list of keys to try for JWT verification (supports rotation).

        If jwt_secret_keys is set (comma-separated), returns all keys.
        Otherwise returns just the single jwt_secret_key.
        The first key is always the signing key.
        """
        if self.jwt_secret_keys:
            keys = [k.strip() for k in self.jwt_secret_keys.split(",") if k.strip()]
            if keys:
                return keys
        return [self.jwt_secret_key]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        """Parse CORS origins from JSON string or list."""
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except (json.JSONDecodeError, TypeError):
                return [origin.strip() for origin in v.split(",")]
        if isinstance(v, list):
            return [str(item) for item in v]
        return ["http://localhost:3000"]

    @model_validator(mode="after")
    def build_derived_urls(self) -> Settings:
        """Build database_url and redis_url from components if not set."""
        if not self.database_url:
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        if not self.redis_url:
            self.redis_url = f"redis://{self.redis_host}:{self.redis_port}/0"
        return self


@functools.lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
