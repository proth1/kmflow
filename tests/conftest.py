"""Shared test fixtures for the KMFlow test suite.

Provides mock database sessions, test settings, and a FastAPI
test client configured with overridden dependencies.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.auth import get_current_user
from src.core.config import Settings, get_settings
from src.core.models import User, UserRole


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings that don't connect to real services."""
    return Settings(
        app_env="testing",
        debug=False,
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="kmflow_test",
        postgres_user="kmflow_test",
        postgres_password="test_password",
        database_url="postgresql+asyncpg://kmflow_test:test_password@localhost:5432/kmflow_test",
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="test_password",
        redis_host="localhost",
        redis_port=6379,
        redis_url="redis://localhost:6379/1",
        cors_origins=["http://localhost:3000"],
        monitoring_worker_count=0,
    )


def _default_refresh_side_effect(obj: Any) -> None:
    """Simulate session.refresh by ensuring the object has an id."""
    if hasattr(obj, "id") and obj.id is None:
        obj.id = uuid.uuid4()


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create a mock async database session.

    Note: session.add() is synchronous in SQLAlchemy, so we use
    MagicMock for it. All async methods (execute, commit, flush,
    refresh, rollback, close) use AsyncMock.
    """
    session = AsyncMock()
    # execute returns a sync MagicMock result object so that
    # result.scalar_one_or_none(), result.scalars().all(), etc. work
    # without awaiting (they are sync in SQLAlchemy).
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock(side_effect=_default_refresh_side_effect)
    session.delete = AsyncMock()
    # session.add is synchronous in real SQLAlchemy
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_neo4j_driver() -> MagicMock:
    """Create a mock Neo4j driver."""
    driver = MagicMock()
    driver.verify_connectivity = AsyncMock(return_value=None)
    driver.close = AsyncMock()
    driver.session = MagicMock()
    return driver


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Create a mock Redis client."""
    client = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    client.aclose = AsyncMock()
    # get returns None by default (no token blacklisted)
    client.get = AsyncMock(return_value=None)
    client.setex = AsyncMock()
    # Redis Streams support
    client.xadd = AsyncMock(return_value="1-0")
    client.xread = AsyncMock(return_value=[])
    client.xreadgroup = AsyncMock(return_value=[])
    client.xack = AsyncMock(return_value=1)
    client.xgroup_create = AsyncMock()
    # Pub/Sub support
    client.publish = AsyncMock(return_value=0)
    client.pubsub = MagicMock()
    return client


class MockSessionFactory:
    """A callable that returns an async context manager yielding a mock session.

    This mimics the behavior of `async_sessionmaker()` which produces
    sessions via `async with session_factory() as session:`.
    """

    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    def __call__(self) -> MockSessionFactory:
        return self

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


@pytest.fixture
async def test_app(
    mock_db_session: AsyncMock,
    mock_neo4j_driver: MagicMock,
    mock_redis_client: AsyncMock,
) -> AsyncGenerator[Any, None]:
    """Create a test FastAPI application with mocked dependencies.

    The lifespan is skipped; instead, we manually set app.state
    with mock objects.
    """
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware

    from src.api.middleware.security import (
        RateLimitMiddleware,
        RequestIDMiddleware,
        SecurityHeadersMiddleware,
    )
    from src.api.routes import (
        admin,
        auth,
        camunda,
        conformance,
        copilot,
        dashboard,
        engagements,
        evidence,
        gdpr,
        governance,
        graph,
        health,
        integrations,
        lineage,
        metrics,
        monitoring,
        patterns,
        portal,
        pov,
        regulatory,
        reports,
        shelf_requests,
        simulations,
        taskmining,
        tom,
        users,
        websocket,
    )
    from src.api.routes import (
        annotations as annotations_routes,
    )
    from src.mcp.server import router as mcp_router

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        yield

    app = FastAPI(lifespan=test_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=100,
        window_seconds=60,
    )

    # Phase 1-2 routes
    app.include_router(health.router)
    app.include_router(engagements.router)
    app.include_router(evidence.router)
    app.include_router(shelf_requests.router)
    app.include_router(graph.router)
    app.include_router(pov.router)
    app.include_router(dashboard.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(regulatory.router)
    app.include_router(tom.router)
    app.include_router(integrations.router)
    app.include_router(reports.router)

    # Phase 3 routes
    app.include_router(monitoring.router)
    app.include_router(websocket.router)
    app.include_router(patterns.router)
    app.include_router(simulations.router)
    app.include_router(portal.router)
    app.include_router(mcp_router)
    app.include_router(camunda.router)

    # Phase 4 routes
    app.include_router(copilot.router)
    app.include_router(conformance.router)

    # Phase 8 routes
    app.include_router(metrics.router)
    app.include_router(annotations_routes.router)

    # Data layer routes
    app.include_router(lineage.router)
    app.include_router(governance.router)
    app.include_router(admin.router)
    app.include_router(gdpr.router)
    app.include_router(taskmining.router)

    # Override get_settings so auth uses the same JWT secret as tests
    test_settings_instance = Settings(
        jwt_secret_key="test-secret-key-for-tests",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        jwt_refresh_token_expire_minutes=10080,
        auth_dev_mode=True,
        monitoring_worker_count=0,
    )
    app.dependency_overrides[get_settings] = lambda: test_settings_instance

    # Override get_current_user so all require_permission deps resolve
    # without needing a real JWT token in test requests.
    # Auth-specific tests clear this override via their own fixture.
    mock_user = MagicMock(spec=User)
    mock_user.id = uuid.uuid4()
    mock_user.email = "testuser@kmflow.dev"
    mock_user.name = "Test User"
    mock_user.role = UserRole.PLATFORM_ADMIN  # Admin so all permissions pass
    mock_user.is_active = True
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Set mock state using the proper session factory mock
    app.state.db_session_factory = MockSessionFactory(mock_db_session)
    app.state.db_engine = MagicMock()
    app.state.neo4j_driver = mock_neo4j_driver
    app.state.redis_client = mock_redis_client

    yield app


@pytest.fixture
async def client(test_app: Any) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP test client."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
