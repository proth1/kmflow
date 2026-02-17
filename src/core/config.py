"""Application configuration using Pydantic Settings v2.

Loads configuration from environment variables with .env file support.
All settings are validated at startup and available as typed attributes.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import field_validator, model_validator
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
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]

    # ── Embeddings ───────────────────────────────────────────────
    embedding_model: str = "all-mpnet-base-v2"
    embedding_dimension: int = 768

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


def get_settings() -> Settings:
    """Create and return application settings instance."""
    return Settings()
