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

from src.core.config import Settings


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
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock(side_effect=_default_refresh_side_effect)
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
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from src.api.routes import engagements, health

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
    app.include_router(health.router)
    app.include_router(engagements.router)

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
