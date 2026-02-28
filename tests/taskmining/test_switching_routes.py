"""Tests for switching sequence API routes.

Covers GET /switching/traces, GET /switching/matrix,
GET /switching/friction, POST /switching/assemble.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from src.core.models.taskmining import SwitchingTrace, TransitionMatrix

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_trace_orm(
    engagement_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    friction_score: float = 0.3,
    is_ping_pong: bool = False,
    trace_sequence: list[str] | None = None,
) -> MagicMock:
    t = MagicMock(spec=SwitchingTrace)
    t.id = uuid.uuid4()
    t.engagement_id = engagement_id or uuid.uuid4()
    t.session_id = session_id or uuid.uuid4()
    t.role_id = None
    t.trace_sequence = trace_sequence or ["Excel", "Chrome"]
    t.dwell_durations = [5000, 0]
    t.total_duration_ms = 5000
    t.friction_score = friction_score
    t.is_ping_pong = is_ping_pong
    t.ping_pong_count = None
    t.app_count = 2
    t.started_at = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
    t.ended_at = datetime(2026, 2, 1, 9, 1, tzinfo=UTC)
    t.created_at = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
    return t


def _make_matrix_orm(engagement_id: uuid.UUID | None = None) -> MagicMock:
    m = MagicMock(spec=TransitionMatrix)
    m.id = uuid.uuid4()
    m.engagement_id = engagement_id or uuid.uuid4()
    m.role_id = None
    m.period_start = datetime(2026, 2, 1, 0, 0, tzinfo=UTC)
    m.period_end = datetime(2026, 2, 1, 23, 59, tzinfo=UTC)
    m.matrix_data = {"Excel": {"Chrome": 5}, "Chrome": {"Excel": 3}}
    m.total_transitions = 8
    m.unique_apps = 2
    m.top_transitions = [{"from_app": "Excel", "to_app": "Chrome", "count": 5}]
    m.created_at = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
    return m


# ---------------------------------------------------------------------------
# GET /switching/traces
# ---------------------------------------------------------------------------


class TestGetSwitchingTraces:
    @pytest.mark.asyncio
    async def test_returns_traces_for_engagement(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        engagement_id = uuid.uuid4()
        trace = _make_trace_orm(engagement_id=engagement_id)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [trace]
        result_mock.scalar.return_value = 1
        mock_db_session.execute = AsyncMock(return_value=result_mock)

        response = await client.get(
            "/api/v1/taskmining/switching/traces",
            params={"engagement_id": str(engagement_id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_requires_engagement_id(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/taskmining/switching/traces")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_list_when_no_traces(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        result_mock.scalar.return_value = 0
        mock_db_session.execute = AsyncMock(return_value=result_mock)

        response = await client.get(
            "/api/v1/taskmining/switching/traces",
            params={"engagement_id": str(uuid.uuid4())},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_min_friction_filter_accepted(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        result_mock.scalar.return_value = 0
        mock_db_session.execute = AsyncMock(return_value=result_mock)

        response = await client.get(
            "/api/v1/taskmining/switching/traces",
            params={"engagement_id": str(uuid.uuid4()), "min_friction": 0.5},
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /switching/matrix
# ---------------------------------------------------------------------------


class TestGetTransitionMatrix:
    @pytest.mark.asyncio
    async def test_returns_existing_matrix(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        engagement_id = uuid.uuid4()
        matrix = _make_matrix_orm(engagement_id=engagement_id)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = matrix
        mock_db_session.execute = AsyncMock(return_value=result_mock)

        response = await client.get(
            "/api/v1/taskmining/switching/matrix",
            params={
                "engagement_id": str(engagement_id),
                "period_start": "2026-02-01T00:00:00Z",
                "period_end": "2026-02-01T23:59:00Z",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "matrix_data" in data
        assert data["total_transitions"] == 8

    @pytest.mark.asyncio
    async def test_requires_engagement_and_period(self, client: AsyncClient) -> None:
        # Missing period_start and period_end
        response = await client.get(
            "/api/v1/taskmining/switching/matrix",
            params={"engagement_id": str(uuid.uuid4())},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_computes_matrix_when_none_exists(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        engagement_id = uuid.uuid4()
        computed_matrix = _make_matrix_orm(engagement_id=engagement_id)

        # First execute returns None (no existing matrix), second returns the computed matrix
        none_result = MagicMock()
        none_result.scalar_one_or_none.return_value = None

        # Empty events result for the compute call
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []

        refresh_result = MagicMock()
        refresh_result.scalar_one_or_none.return_value = computed_matrix

        mock_db_session.execute = AsyncMock(side_effect=[none_result, empty_result])
        mock_db_session.flush = AsyncMock()
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", computed_matrix.id))

        with patch(
            "src.api.routes.taskmining.compute_transition_matrix",
            new=AsyncMock(return_value=computed_matrix),
        ):
            response = await client.get(
                "/api/v1/taskmining/switching/matrix",
                params={
                    "engagement_id": str(engagement_id),
                    "period_start": "2026-02-01T00:00:00Z",
                    "period_end": "2026-02-01T23:59:00Z",
                },
            )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /switching/friction
# ---------------------------------------------------------------------------


class TestGetFrictionAnalysis:
    @pytest.mark.asyncio
    async def test_returns_friction_summary(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        engagement_id = uuid.uuid4()

        expected_result = {
            "avg_friction_score": 0.42,
            "high_friction_traces": [],
            "top_ping_pong_pairs": [],
            "total_traces_analyzed": 3,
        }

        with patch(
            "src.api.routes.taskmining.get_friction_analysis",
            new=AsyncMock(return_value=expected_result),
        ):
            response = await client.get(
                "/api/v1/taskmining/switching/friction",
                params={"engagement_id": str(engagement_id)},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["avg_friction_score"] == pytest.approx(0.42)
        assert data["total_traces_analyzed"] == 3

    @pytest.mark.asyncio
    async def test_requires_engagement_id(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/taskmining/switching/friction")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_zeros_for_empty_engagement(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        empty_result = {
            "avg_friction_score": 0.0,
            "high_friction_traces": [],
            "top_ping_pong_pairs": [],
            "total_traces_analyzed": 0,
        }

        with patch(
            "src.api.routes.taskmining.get_friction_analysis",
            new=AsyncMock(return_value=empty_result),
        ):
            response = await client.get(
                "/api/v1/taskmining/switching/friction",
                params={"engagement_id": str(uuid.uuid4())},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total_traces_analyzed"] == 0


# ---------------------------------------------------------------------------
# POST /switching/assemble
# ---------------------------------------------------------------------------


class TestAssembleSwitching:
    @pytest.mark.asyncio
    async def test_assemble_triggers_trace_assembly(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        engagement_id = uuid.uuid4()

        mock_trace = _make_trace_orm(engagement_id=engagement_id)
        with patch(
            "src.api.routes.taskmining.assemble_switching_traces",
            new=AsyncMock(return_value=[mock_trace, mock_trace]),
        ):
            response = await client.post(
                "/api/v1/taskmining/switching/assemble",
                json={"engagement_id": str(engagement_id)},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["traces_created"] == 2
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_assemble_with_session_id(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        engagement_id = uuid.uuid4()
        session_id = uuid.uuid4()

        with patch(
            "src.api.routes.taskmining.assemble_switching_traces",
            new=AsyncMock(return_value=[]),
        ):
            response = await client.post(
                "/api/v1/taskmining/switching/assemble",
                json={
                    "engagement_id": str(engagement_id),
                    "session_id": str(session_id),
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["traces_created"] == 0

    @pytest.mark.asyncio
    async def test_assemble_requires_engagement_id(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/taskmining/switching/assemble",
            json={},
        )
        assert response.status_code == 422
