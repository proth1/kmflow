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
    db_pool_size: int = 20
    db_max_overflow: int = 10

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
    auth_dev_mode: bool = False  # Allow local dev tokens
    encryption_key: str = "dev-encryption-key-change-in-production"

    # ── Cookie Auth (Issue #156) ──────────────────────────────────
    # cookie_domain: Set to the shared domain (e.g. ".example.com") for
    # multi-subdomain deployments, or leave empty to default to the
    # request host (suitable for single-host deployments).
    cookie_domain: str = ""
    # cookie_secure: Must be True in production (HTTPS required for
    # Secure cookies). Defaults to True; set False only in local dev.
    cookie_secure: bool = True

    # ── RAG Copilot (Phase 4) ─────────────────────────────────────
    copilot_model: str = "claude-sonnet-4-5-20250929"
    copilot_max_context_tokens: int = 4000
    copilot_max_response_tokens: int = 2000

    # ── Simulation Suggester ──────────────────────────────────────
    suggester_model: str = "claude-sonnet-4-5-20250929"

    # ── WebSocket Limits (Phase 4) ────────────────────────────────
    ws_max_connections_per_engagement: int = 10

    # ── Rate Limiting ─────────────────────────────────────────────
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # ── Copilot Rate Limiting (Phase 5) ─────────────────────────
    copilot_rate_limit_per_user: int = 10
    copilot_rate_limit_window: int = 60  # seconds

    # ── Data Retention (Phase 5) ──────────────────────────────
    # TODO(DPA): GDPR Article 28 requires Data Processing Agreements between the
    # platform operator and each client. Retention periods below must align with
    # agreed DPA terms. See docs/audit-findings/D2-compliance.md for full context.
    retention_cleanup_enabled: bool = False
    evidence_retention_days: int = 365  # Default: 1 year; override per DPA terms
    audit_retention_days: int = 730  # Default: 2 years; regulatory minimum may vary

    # ── GDPR (Issue #165) ────────────────────────────────────
    # Grace period before erasure is executed after a subject request.
    # During this window the user can cancel their erasure request.
    # A background job (not yet implemented) should anonymize the account
    # once erasure_scheduled_at passes.
    gdpr_erasure_grace_days: int = 30

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

    # ── Task Mining ───────────────────────────────────────────────
    taskmining_enabled: bool = False
    taskmining_worker_count: int = 1
    taskmining_stream_max_len: int = 10000
    taskmining_event_retention_days: int = 90
    taskmining_action_retention_days: int = 365
    taskmining_pii_quarantine_hours: int = 24
    taskmining_batch_max_size: int = 1000

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

    @model_validator(mode="after")
    def reject_default_secrets_in_production(self) -> Settings:
        """Block startup when default development secrets are present outside development."""
        if self.app_env == "development":
            return self
        has_default_jwt = "dev-secret-key" in self.jwt_secret_key
        has_default_enc = "dev-encryption-key" in self.encryption_key
        has_default_pg = self.postgres_password == "kmflow_dev_password"
        has_default_neo4j = self.neo4j_password == "neo4j_dev_password"
        problems: list[str] = []
        if has_default_jwt:
            problems.append("JWT_SECRET_KEY")
        if has_default_enc:
            problems.append("ENCRYPTION_KEY")
        if has_default_pg:
            problems.append("POSTGRES_PASSWORD")
        if has_default_neo4j:
            problems.append("NEO4J_PASSWORD")
        if self.auth_dev_mode:
            problems.append("AUTH_DEV_MODE=false")
        if self.debug:
            problems.append("DEBUG=false")
        if problems:
            raise ValueError(
                "FATAL: Default development secrets detected in non-development environment. "
                f"Set: {', '.join(problems)}"
            )
        return self


@functools.lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
