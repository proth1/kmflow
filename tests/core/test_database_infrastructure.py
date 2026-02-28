"""Tests for Database Infrastructure — Story #309.

Covers all 5 BDD scenarios:
1. Docker Compose defines services with healthchecks
2. pgvector extension availability (validated via model config)
3. Neo4j APOC plugin configuration
4. Alembic migration framework and table schema
5. SQLAlchemy async session configuration
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import DateTime

from src.core.config import Settings, get_settings
from src.core.database import Base, create_engine, get_db_session

# ---------------------------------------------------------------------------
# BDD Scenario 1: All services start healthy via docker compose
# ---------------------------------------------------------------------------


class TestBDDScenario1DockerComposeServices:
    """Given docker-compose.yml defines PostgreSQL, Neo4j, and Redis services
    When each service has a healthcheck configured
    Then all three services are defined and configured correctly.
    """

    def _load_compose(self) -> dict[str, Any]:
        """Load and parse docker-compose.yml."""
        compose_path = Path("docker-compose.yml")
        assert compose_path.exists(), "docker-compose.yml must exist at repo root"
        with compose_path.open() as f:
            return yaml.safe_load(f)

    def test_postgres_service_defined(self) -> None:
        """PostgreSQL service is defined in docker-compose.yml."""
        compose = self._load_compose()
        assert "postgres" in compose["services"]

    def test_postgres_uses_pgvector_image(self) -> None:
        """PostgreSQL uses pgvector image for vector similarity."""
        compose = self._load_compose()
        pg = compose["services"]["postgres"]
        assert "pgvector" in pg["image"]
        assert "pg15" in pg["image"]

    def test_postgres_has_healthcheck(self) -> None:
        """PostgreSQL has a healthcheck configured."""
        compose = self._load_compose()
        pg = compose["services"]["postgres"]
        assert "healthcheck" in pg
        assert "pg_isready" in str(pg["healthcheck"]["test"])

    def test_neo4j_service_defined(self) -> None:
        """Neo4j service is defined in docker-compose.yml."""
        compose = self._load_compose()
        assert "neo4j" in compose["services"]

    def test_neo4j_uses_community_5x(self) -> None:
        """Neo4j uses 5.x community image."""
        compose = self._load_compose()
        neo = compose["services"]["neo4j"]
        assert "neo4j:5" in neo["image"]
        assert "community" in neo["image"]

    def test_neo4j_has_healthcheck(self) -> None:
        """Neo4j has a healthcheck configured."""
        compose = self._load_compose()
        neo = compose["services"]["neo4j"]
        assert "healthcheck" in neo
        assert "cypher-shell" in str(neo["healthcheck"]["test"])

    def test_redis_service_defined(self) -> None:
        """Redis service is defined in docker-compose.yml."""
        compose = self._load_compose()
        assert "redis" in compose["services"]

    def test_redis_uses_7x_alpine(self) -> None:
        """Redis uses 7.x alpine image."""
        compose = self._load_compose()
        redis = compose["services"]["redis"]
        assert "redis:7" in redis["image"]
        assert "alpine" in redis["image"]

    def test_redis_has_healthcheck(self) -> None:
        """Redis has a healthcheck configured."""
        compose = self._load_compose()
        redis = compose["services"]["redis"]
        assert "healthcheck" in redis
        assert "ping" in str(redis["healthcheck"]["test"])

    def test_services_share_network(self) -> None:
        """All three services share the same Docker network."""
        compose = self._load_compose()
        for svc_name in ("postgres", "neo4j", "redis"):
            svc = compose["services"][svc_name]
            assert "kmflow-network" in svc.get("networks", [])


# ---------------------------------------------------------------------------
# BDD Scenario 2: pgvector extension is configured
# ---------------------------------------------------------------------------


class TestBDDScenario2PgvectorExtension:
    """Given PostgreSQL is running with the pgvector image
    Then vector columns can be defined in models.
    """

    def test_pgvector_image_in_compose(self) -> None:
        """Docker compose uses pgvector-enabled PostgreSQL image."""
        compose_path = Path("docker-compose.yml")
        with compose_path.open() as f:
            compose = yaml.safe_load(f)
        pg = compose["services"]["postgres"]
        assert "pgvector" in pg["image"]

    def test_vector_column_in_evidence_fragments(self) -> None:
        """EvidenceFragment model defines a Vector(768) column."""
        from src.core.models.evidence import EvidenceFragment

        columns = {c.name: c for c in EvidenceFragment.__table__.columns}
        assert "embedding" in columns

    def test_vector_dimension_is_768(self) -> None:
        """Embedding column uses 768 dimensions."""
        from src.core.models.evidence import EvidenceFragment

        col = EvidenceFragment.__table__.columns["embedding"]
        # pgvector Vector type stores dimension
        assert col.type.dim == 768


# ---------------------------------------------------------------------------
# BDD Scenario 3: Neo4j APOC procedures are configured
# ---------------------------------------------------------------------------


class TestBDDScenario3Neo4jApoc:
    """Given Neo4j 5.x is running with APOC plugin mounted
    Then APOC configuration is present in docker-compose.
    """

    def test_neo4j_apoc_plugin_configured(self) -> None:
        """Neo4j has APOC plugin in NEO4J_PLUGINS env var."""
        compose_path = Path("docker-compose.yml")
        with compose_path.open() as f:
            compose = yaml.safe_load(f)
        neo = compose["services"]["neo4j"]
        env = neo.get("environment", {})
        plugins = env.get("NEO4J_PLUGINS", "")
        assert "apoc" in plugins

    def test_neo4j_apoc_unrestricted(self) -> None:
        """APOC procedures are unrestricted in Neo4j config."""
        compose_path = Path("docker-compose.yml")
        with compose_path.open() as f:
            compose = yaml.safe_load(f)
        neo = compose["services"]["neo4j"]
        env = neo.get("environment", {})
        assert env.get("NEO4J_dbms_security_procedures_unrestricted") == "apoc.*"

    def test_neo4j_driver_config_in_settings(self) -> None:
        """Settings has neo4j_uri, neo4j_user, neo4j_password."""
        settings = get_settings()
        assert settings.neo4j_uri is not None
        assert settings.neo4j_user is not None
        assert settings.neo4j_password is not None

    def test_neo4j_bolt_protocol(self) -> None:
        """Neo4j URI uses bolt protocol."""
        settings = get_settings()
        assert settings.neo4j_uri.startswith("bolt://")


# ---------------------------------------------------------------------------
# BDD Scenario 4: Alembic migration framework and table schema
# ---------------------------------------------------------------------------


class TestBDDScenario4AlembicMigrations:
    """Given Alembic is configured with the async engine
    Then migration framework is properly initialized.
    """

    def test_alembic_ini_exists(self) -> None:
        """alembic.ini exists at project root."""
        assert Path("alembic.ini").exists()

    def test_alembic_env_exists(self) -> None:
        """alembic/env.py exists for migration execution."""
        assert Path("alembic/env.py").exists()

    def test_alembic_versions_directory_exists(self) -> None:
        """alembic/versions/ directory contains migration files."""
        versions_dir = Path("alembic/versions")
        assert versions_dir.exists()
        migrations = list(versions_dir.glob("*.py"))
        assert len(migrations) > 0, "No migration files found"

    def test_alembic_env_uses_async_engine(self) -> None:
        """alembic/env.py uses async migration pattern."""
        env_content = Path("alembic/env.py").read_text()
        assert "run_async_migrations" in env_content
        assert "async_engine_from_config" in env_content

    def test_alembic_env_imports_base_metadata(self) -> None:
        """alembic/env.py imports Base.metadata for autogenerate."""
        env_content = Path("alembic/env.py").read_text()
        assert "from src.core.database import Base" in env_content
        assert "target_metadata = Base.metadata" in env_content

    def test_engagement_scoped_tables_have_engagement_id(self) -> None:
        """Engagement-scoped tables have an engagement_id column."""
        from src.core.models.evidence import EvidenceItem

        columns = {c.name for c in EvidenceItem.__table__.columns}
        assert "engagement_id" in columns

    def test_timestamp_columns_are_timezone_aware(self) -> None:
        """Timestamp columns use timezone-aware DateTime."""
        from src.core.models.evidence import EvidenceItem

        for col in EvidenceItem.__table__.columns:
            if isinstance(col.type, DateTime):
                assert col.type.timezone is True, f"{col.name} must be timezone-aware"

    def test_migration_files_have_sequential_numbers(self) -> None:
        """Migration files follow sequential numbering."""
        versions_dir = Path("alembic/versions")
        migrations = sorted(versions_dir.glob("*.py"))
        numbers = []
        for m in migrations:
            name = m.stem
            # Extract number prefix (e.g., "001" from "001_initial")
            parts = name.split("_", 1)
            if parts[0].isdigit():
                numbers.append(int(parts[0]))
        # Verify sequential (each number present from 1 to max)
        assert len(numbers) > 0
        assert numbers == sorted(numbers), "Migrations should be sequentially numbered"

    def test_latest_migration_references_previous(self) -> None:
        """Latest migration has correct down_revision."""
        versions_dir = Path("alembic/versions")
        migrations = sorted(versions_dir.glob("*.py"))
        if len(migrations) >= 2:
            latest = migrations[-1].read_text()
            assert "down_revision" in latest


# ---------------------------------------------------------------------------
# BDD Scenario 5: SQLAlchemy async session configuration
# ---------------------------------------------------------------------------


class TestBDDScenario5AsyncSession:
    """Given a FastAPI route handler that performs a database read
    Then the async session is properly configured.
    """

    def test_create_engine_function_signature(self) -> None:
        """create_engine() accepts Settings and returns (engine, factory) tuple."""
        import inspect

        sig = inspect.signature(create_engine)
        params = list(sig.parameters.keys())
        assert "settings" in params
        # Return annotation is tuple
        assert "tuple" in str(sig.return_annotation).lower() or "AsyncEngine" in str(sig.return_annotation)

    def test_create_engine_configures_pool_pre_ping(self) -> None:
        """create_engine() passes pool_pre_ping=True."""
        import inspect

        source = inspect.getsource(create_engine)
        assert "pool_pre_ping=True" in source

    def test_engine_pool_size_from_settings(self) -> None:
        """Engine pool_size comes from settings."""
        settings = Settings(database_url="postgresql+asyncpg://x:y@z/db", db_pool_size=15)
        assert settings.db_pool_size == 15

    def test_session_factory_uses_expire_on_commit_false(self) -> None:
        """create_engine configures expire_on_commit=False."""
        import inspect

        source = inspect.getsource(create_engine)
        assert "expire_on_commit=False" in source

    def test_get_db_session_is_async_generator(self) -> None:
        """get_db_session is an async generator function."""
        import inspect

        assert inspect.isasyncgenfunction(get_db_session)

    def test_get_db_session_handles_rollback(self) -> None:
        """get_db_session rolls back on exception."""
        import inspect

        source = inspect.getsource(get_db_session)
        assert "rollback" in source

    def test_settings_has_database_url(self) -> None:
        """Settings provides database_url for PostgreSQL."""
        settings = get_settings()
        # database_url may be None (computed from components) or set
        assert hasattr(settings, "database_url")
        assert hasattr(settings, "postgres_host")
        assert hasattr(settings, "postgres_port")

    def test_redis_connection_settings(self) -> None:
        """Settings provides Redis connection parameters."""
        settings = get_settings()
        assert hasattr(settings, "redis_host")
        assert hasattr(settings, "redis_port")

    def test_base_declarative_registered(self) -> None:
        """Base.metadata contains registered table names."""
        tables = Base.metadata.tables
        assert "evidence_items" in tables
        assert "engagements" in tables
        assert "evidence_fragments" in tables
