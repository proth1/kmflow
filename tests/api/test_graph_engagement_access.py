"""Tests for graph route engagement access control.

Verifies that graph endpoints enforce engagement membership checks,
blocking non-member users from accessing engagement-scoped graph data.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.auth import get_current_user
from src.core.config import Settings, get_settings
from src.core.models import User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_ENG_ID = str(uuid.uuid4())


def _make_non_member() -> MagicMock:
    """Create a non-admin, non-member user for access control testing."""
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "outsider@kmflow.dev"
    user.name = "Outsider"
    user.role = UserRole.PROCESS_ANALYST
    user.is_active = True
    return user


def _make_admin_user() -> MagicMock:
    """Create a platform admin user."""
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "admin@kmflow.dev"
    user.name = "Admin"
    user.role = UserRole.PLATFORM_ADMIN
    user.is_active = True
    return user


@asynccontextmanager
async def _noop_lifespan(app: FastAPI):  # noqa: ANN001
    yield


def _make_session_mock(member_result: Any = None) -> AsyncMock:
    """Create a mock DB session that returns the given membership result."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = member_result
    mock_result.scalar.return_value = 0
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


class MockSessionFactory:
    """Callable that returns an async context manager yielding a mock session."""

    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    def __call__(self) -> MockSessionFactory:
        return self

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *args: Any) -> None:
        pass


def _build_graph_app(user: MagicMock, session: AsyncMock) -> FastAPI:
    """Build a minimal FastAPI app with only the graph router."""
    from src.api.routes import graph

    app = FastAPI(lifespan=_noop_lifespan)
    app.include_router(graph.router)

    test_settings = Settings(
        jwt_secret_key="test-key",
        jwt_algorithm="HS256",
        auth_dev_mode=True,
        debug=True,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: test_settings

    app.state.db_session_factory = MockSessionFactory(session)
    app.state.db_engine = MagicMock()
    app.state.neo4j_driver = MagicMock()
    app.state.redis_client = AsyncMock()

    return app


# ---------------------------------------------------------------------------
# /graph/build engagement access
# ---------------------------------------------------------------------------


class TestBuildEngagementAccess:
    """POST /api/v1/graph/build must enforce engagement membership."""

    @pytest.mark.asyncio
    async def test_build_returns_403_for_non_member(self) -> None:
        """Non-member user should get 403 on POST /graph/build."""
        user = _make_non_member()
        # DB returns None → no EngagementMember record → 403
        session = _make_session_mock(member_result=None)
        app = _build_graph_app(user, session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/graph/build",
                json={"engagement_id": FAKE_ENG_ID},
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.KnowledgeGraphBuilder")
    @patch("src.api.routes.graph.KnowledgeGraphService")
    @patch("src.api.routes.graph.EmbeddingService")
    async def test_build_succeeds_for_admin_regardless_of_membership(
        self,
        mock_emb_cls: MagicMock,
        mock_graph_cls: MagicMock,
        mock_builder_cls: MagicMock,
    ) -> None:
        """Platform admin bypasses engagement membership check."""
        from src.semantic.builder import BuildResult

        admin = _make_admin_user()
        session = _make_session_mock(member_result=None)
        app = _build_graph_app(admin, session)

        mock_builder = AsyncMock()
        mock_builder.build_knowledge_graph = AsyncMock(
            return_value=BuildResult(
                engagement_id=FAKE_ENG_ID,
                node_count=0,
                relationship_count=0,
                nodes_by_label={},
                relationships_by_type={},
                fragments_processed=0,
                entities_extracted=0,
                entities_resolved=0,
            )
        )
        mock_builder_cls.return_value = mock_builder

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/graph/build",
                json={"engagement_id": FAKE_ENG_ID},
            )
        assert response.status_code == 202


# ---------------------------------------------------------------------------
# /graph/traverse/{node_id} — permission guard
# ---------------------------------------------------------------------------


class TestTraverseAccess:
    """GET /api/v1/graph/traverse/{node_id} requires authentication."""

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.KnowledgeGraphService")
    async def test_traverse_returns_200_for_authenticated_user(
        self,
        mock_graph_cls: MagicMock,
    ) -> None:
        """Authenticated user with engagement:read should get 200."""
        from src.semantic.graph import GraphNode

        user = _make_admin_user()
        session = _make_session_mock()
        app = _build_graph_app(user, session)

        mock_graph_service = AsyncMock()
        mock_graph_service.traverse = AsyncMock(
            return_value=[
                GraphNode(id="node-1", label="Activity", properties={"name": "Check"}),
            ]
        )
        mock_graph_cls.return_value = mock_graph_service

        node_id = str(uuid.uuid4())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                f"/api/v1/graph/traverse/{node_id}",
                params={"engagement_id": str(uuid.uuid4())},
            )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_traverse_accepts_pagination_params(self) -> None:
        """Traverse endpoint accepts depth and relationship_types params."""

        user = _make_admin_user()
        session = _make_session_mock()
        app = _build_graph_app(user, session)

        with patch("src.api.routes.graph.KnowledgeGraphService") as mock_cls:
            mock_service = AsyncMock()
            mock_service.traverse = AsyncMock(return_value=[])
            mock_cls.return_value = mock_service

            node_id = str(uuid.uuid4())
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get(
                    f"/api/v1/graph/traverse/{node_id}",
                    params={
                        "engagement_id": str(uuid.uuid4()),
                        "depth": 3,
                        "relationship_types": "SUPPORTS,LINKS_TO",
                    },
                )
            assert response.status_code == 200


# ---------------------------------------------------------------------------
# /graph/search — permission guard
# ---------------------------------------------------------------------------


class TestSearchAccess:
    """GET /api/v1/graph/search requires authentication."""

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.EmbeddingService")
    async def test_search_returns_200_for_authenticated_user(
        self,
        mock_emb_cls: MagicMock,
    ) -> None:
        """Authenticated user with engagement:read should get 200."""
        user = _make_admin_user()
        session = _make_session_mock()
        app = _build_graph_app(user, session)

        mock_emb_service = AsyncMock()
        mock_emb_service.search_by_text = AsyncMock(return_value=[])
        mock_emb_cls.return_value = mock_emb_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/graph/search",
                params={"query": "credit check process", "top_k": 5},
            )
        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.EmbeddingService")
    async def test_search_accepts_engagement_scope_and_pagination(
        self,
        mock_emb_cls: MagicMock,
    ) -> None:
        """Search endpoint accepts engagement_id scoping and top_k param."""
        user = _make_admin_user()
        session = _make_session_mock()
        app = _build_graph_app(user, session)

        mock_emb_service = AsyncMock()
        mock_emb_service.search_by_text = AsyncMock(return_value=[])
        mock_emb_cls.return_value = mock_emb_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/graph/search",
                params={
                    "query": "approval workflow",
                    "top_k": 10,
                    "engagement_id": FAKE_ENG_ID,
                },
            )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# /{engagement_id}/stats — require_engagement_access
# ---------------------------------------------------------------------------


class TestStatsEngagementAccess:
    """GET /api/v1/graph/{engagement_id}/stats enforces membership."""

    @pytest.mark.asyncio
    async def test_stats_returns_403_for_non_member(self) -> None:
        """Non-member should receive 403 on stats endpoint."""
        user = _make_non_member()
        session = _make_session_mock(member_result=None)
        app = _build_graph_app(user, session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/graph/{FAKE_ENG_ID}/stats")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# /{engagement_id}/subgraph — require_engagement_access
# ---------------------------------------------------------------------------


class TestSubgraphEngagementAccess:
    """GET /api/v1/graph/{engagement_id}/subgraph enforces membership."""

    @pytest.mark.asyncio
    async def test_subgraph_returns_403_for_non_member(self) -> None:
        """Non-member should receive 403 on subgraph endpoint."""
        user = _make_non_member()
        session = _make_session_mock(member_result=None)
        app = _build_graph_app(user, session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/graph/{FAKE_ENG_ID}/subgraph")
        assert response.status_code == 403
