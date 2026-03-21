"""Tests for pipeline quality API routes (src/api/routes/pipeline_quality.py).

All tests use httpx AsyncClient with ASGITransport wrapping the FastAPI app.
Database and auth dependencies are overridden to avoid real connections.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import get_session
from src.api.main import create_app
from src.core.models import User, UserRole
from src.core.permissions import require_engagement_access

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "tester@kmflow.dev"
    user.role = UserRole.PLATFORM_ADMIN
    user.is_active = True
    return user


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.all.return_value = []
    result.scalar.return_value = None
    result.scalar_one_or_none.return_value = None
    result.fetchone.return_value = None
    result.first.return_value = None
    session.execute.return_value = result
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _make_app(session: AsyncMock) -> Any:
    """Create the FastAPI app with overridden session and auth dependencies."""
    from src.core.auth import get_current_user

    mock_user = _make_user()
    app = create_app()
    # Override session dependency
    app.dependency_overrides[get_session] = lambda: session
    # Override auth dependency
    app.dependency_overrides[get_current_user] = lambda: mock_user
    # Override engagement access check — just return the mock user
    app.dependency_overrides[require_engagement_access] = lambda: mock_user
    # Provide stub app state so middleware doesn't blow up
    app.state.neo4j_driver = MagicMock()
    return app


# ---------------------------------------------------------------------------
# GET /api/v1/quality/pipeline/{engagement_id}/stages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pipeline_stages_returns_200_empty_list(mock_session: AsyncMock) -> None:
    """When no stage metrics exist the endpoint returns 200 with an empty list."""
    app = _make_app(mock_session)
    eid = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/quality/pipeline/{eid}/stages")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_pipeline_stages_returns_200_with_data(mock_session: AsyncMock) -> None:
    """When stage rows are returned they are shaped as StageSummary objects."""
    eid = uuid.uuid4()

    mock_row = MagicMock()
    mock_row.stage = "ingest"
    mock_row.execution_count = 5
    mock_row.avg_duration_ms = 120.0
    mock_row.total_input = 50
    mock_row.total_output = 48
    mock_row.total_errors = 1

    result = MagicMock()
    result.all.return_value = [mock_row]
    mock_session.execute.return_value = result

    app = _make_app(mock_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/quality/pipeline/{eid}/stages")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["stage"] == "ingest"
    assert data[0]["execution_count"] == 5
    assert data[0]["error_rate"] == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# GET /api/v1/quality/pipeline/{engagement_id}/stage/{stage_name}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pipeline_stage_detail_returns_200(mock_session: AsyncMock) -> None:
    eid = uuid.uuid4()

    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = result

    app = _make_app(mock_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/quality/pipeline/{eid}/stage/ingest")

    assert response.status_code == 200
    data = response.json()
    assert data["stage"] == "ingest"
    assert data["executions"] == []


# ---------------------------------------------------------------------------
# GET /api/v1/quality/copilot/{engagement_id}/satisfaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_copilot_satisfaction_returns_200_zeroed(mock_session: AsyncMock) -> None:
    """When no feedback rows exist the endpoint returns zeroed metrics."""
    eid = uuid.uuid4()

    # Simulate empty result (first() returns a row-like object with total_feedback=0)
    mock_row = MagicMock()
    mock_row.total_feedback = 0

    result = MagicMock()
    result.first.return_value = mock_row
    mock_session.execute.return_value = result

    app = _make_app(mock_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/quality/copilot/{eid}/satisfaction")

    assert response.status_code == 200
    data = response.json()
    assert data["total_feedback"] == 0
    assert data["avg_rating"] == 0.0
    assert data["thumbs_up_count"] == 0
    assert data["thumbs_down_count"] == 0
    assert data["hallucination_reports"] == 0
    assert data["correction_count"] == 0


@pytest.mark.asyncio
async def test_get_copilot_satisfaction_none_first_returns_zeroed(mock_session: AsyncMock) -> None:
    """When first() returns None the endpoint should still return zeroed metrics."""
    eid = uuid.uuid4()

    result = MagicMock()
    result.first.return_value = None
    mock_session.execute.return_value = result

    app = _make_app(mock_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/quality/copilot/{eid}/satisfaction")

    assert response.status_code == 200
    data = response.json()
    assert data["total_feedback"] == 0


# ---------------------------------------------------------------------------
# GET /api/v1/quality/retrieval/{engagement_id}/summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_retrieval_summary_returns_200_no_data(mock_session: AsyncMock) -> None:
    """When no eval run exists the endpoint returns zeroed retrieval metrics."""
    eid = uuid.uuid4()

    result = MagicMock()
    result.first.return_value = None
    mock_session.execute.return_value = result

    app = _make_app(mock_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/quality/retrieval/{eid}/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["eval_run_id"] is None
    assert data["query_count"] == 0
    assert data["avg_mrr"] == 0.0


# ---------------------------------------------------------------------------
# GET /api/v1/quality/graph/{engagement_id}/health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_graph_health_returns_404_when_no_snapshot(mock_session: AsyncMock) -> None:
    """When no snapshot exists the endpoint returns 404."""
    eid = uuid.uuid4()

    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result

    app = _make_app(mock_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/quality/graph/{eid}/health")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/quality/dashboard/{engagement_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_dashboard_returns_200(mock_session: AsyncMock) -> None:
    """Dashboard endpoint aggregates all sub-sections and returns 200."""
    eid = uuid.uuid4()
    app = _make_app(mock_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/quality/dashboard/{eid}")

    assert response.status_code == 200
    data = response.json()
    assert "stages" in data
    assert "retrieval" in data
    assert "entities" in data
    assert "graph_health" in data
    assert "satisfaction" in data


@pytest.mark.asyncio
async def test_get_dashboard_stages_is_list(mock_session: AsyncMock) -> None:
    eid = uuid.uuid4()
    app = _make_app(mock_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/quality/dashboard/{eid}")

    assert response.status_code == 200
    assert isinstance(response.json()["stages"], list)


# ---------------------------------------------------------------------------
# GET /api/v1/quality/entities/{engagement_id}/summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_entity_summary_returns_200(mock_session: AsyncMock) -> None:
    eid = uuid.uuid4()

    # first call: totals, second call: per-type
    totals_row = MagicMock()
    totals_row.total = 0
    totals_row.verified = 0

    totals_result = MagicMock()
    totals_result.first.return_value = totals_row

    type_result = MagicMock()
    type_result.all.return_value = []

    mock_session.execute = AsyncMock(side_effect=[totals_result, type_result])

    app = _make_app(mock_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/quality/entities/{eid}/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["total_annotations"] == 0
    assert data["total_verified"] == 0
    assert data["extraction_results"] == []


# ---------------------------------------------------------------------------
# GET /api/v1/quality/retrieval/{engagement_id}/trends
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_retrieval_trends_returns_200_empty(mock_session: AsyncMock) -> None:
    eid = uuid.uuid4()

    result = MagicMock()
    result.all.return_value = []
    mock_session.execute.return_value = result

    app = _make_app(mock_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/quality/retrieval/{eid}/trends")

    assert response.status_code == 200
    assert response.json() == []
