"""BDD tests for Story #392: Cross-Source Consistency Reporting.

Covers 3 acceptance scenarios:
  1. Disagreement report lists all conflicts with full status
  2. Consistency metrics include agreement rate
  3. POV version trend shows conflict reduction rate
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.routes.consistency import router
from src.core.models.conflict import ConflictObject, MismatchType, ResolutionStatus, ResolutionType
from src.core.models.pov import ProcessModel, ProcessModelStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENG_ID = uuid.uuid4()


def _make_conflict(
    *,
    mismatch_type: MismatchType = MismatchType.SEQUENCE_MISMATCH,
    resolution_status: ResolutionStatus = ResolutionStatus.UNRESOLVED,
    severity: float = 0.5,
    resolution_type: ResolutionType | None = None,
    resolver_id: uuid.UUID | None = None,
    resolved_at: datetime | None = None,
) -> MagicMock:
    obj = MagicMock(spec=ConflictObject)
    obj.id = uuid.uuid4()
    obj.engagement_id = ENG_ID
    obj.mismatch_type = mismatch_type
    obj.resolution_type = resolution_type
    obj.resolution_status = resolution_status
    obj.source_a_id = uuid.uuid4()
    obj.source_b_id = uuid.uuid4()
    obj.severity = severity
    obj.escalation_flag = resolution_status == ResolutionStatus.ESCALATED
    obj.resolution_notes = None
    obj.conflict_detail = None
    obj.resolution_details = None
    obj.resolver_id = resolver_id
    obj.assigned_to = None
    obj.created_at = datetime.now(UTC)
    obj.resolved_at = resolved_at
    return obj


def _make_process_model(
    *,
    version: int = 1,
    element_count: int = 200,
    contradiction_count: int = 0,
    metadata_json: dict | None = None,
    generated_at: datetime | None = None,
) -> MagicMock:
    obj = MagicMock(spec=ProcessModel)
    obj.id = uuid.uuid4()
    obj.engagement_id = ENG_ID
    obj.version = version
    obj.status = ProcessModelStatus.COMPLETED
    obj.element_count = element_count
    obj.contradiction_count = contradiction_count
    obj.metadata_json = metadata_json
    obj.generated_at = generated_at or datetime.now(UTC)
    return obj


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _mock_session():
    session = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Scenario 1: Disagreement report lists all conflicts with full status
# ---------------------------------------------------------------------------


class TestScenario1DisagreementReport:
    """BDD Scenario 1: Disagreement report lists all conflicts with full status."""

    @pytest.mark.asyncio
    async def test_report_includes_all_conflicts(self):
        """Given 15 ConflictObjects, report includes all 15."""
        conflicts = [_make_conflict(severity=0.1 * (i + 1)) for i in range(15)]

        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = conflicts
        session.execute = AsyncMock(return_value=mock_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENG_ID}/reports/disagreement")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["conflicts"]) == 15

    @pytest.mark.asyncio
    async def test_report_has_summary_header(self):
        """Report includes open vs resolved summary in header."""
        conflicts = [
            _make_conflict(resolution_status=ResolutionStatus.UNRESOLVED),
            _make_conflict(resolution_status=ResolutionStatus.UNRESOLVED),
            _make_conflict(
                resolution_status=ResolutionStatus.RESOLVED,
                resolution_type=ResolutionType.NAMING_VARIANT,
                resolved_at=datetime.now(UTC),
            ),
        ]

        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = conflicts
        session.execute = AsyncMock(return_value=mock_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENG_ID}/reports/disagreement")

        summary = resp.json()["summary"]
        assert summary["total_conflicts"] == 3
        assert summary["open_count"] == 2
        assert summary["resolved_count"] == 1

    @pytest.mark.asyncio
    async def test_each_entry_includes_required_fields(self):
        """Each conflict entry includes all required fields."""
        conflict = _make_conflict(
            resolution_status=ResolutionStatus.RESOLVED,
            resolution_type=ResolutionType.TEMPORAL_SHIFT,
            resolver_id=uuid.uuid4(),
            resolved_at=datetime.now(UTC),
        )

        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [conflict]
        session.execute = AsyncMock(return_value=mock_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENG_ID}/reports/disagreement")

        entry = resp.json()["conflicts"][0]
        required_fields = [
            "conflict_id",
            "type",
            "severity",
            "resolution_status",
            "resolution_type",
            "source_a_id",
            "source_b_id",
        ]
        for field in required_fields:
            assert field in entry, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_type_breakdown_in_summary(self):
        """Summary includes per-type breakdown of conflicts."""
        conflicts = [
            _make_conflict(mismatch_type=MismatchType.SEQUENCE_MISMATCH),
            _make_conflict(mismatch_type=MismatchType.SEQUENCE_MISMATCH),
            _make_conflict(mismatch_type=MismatchType.ROLE_MISMATCH),
        ]

        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = conflicts
        session.execute = AsyncMock(return_value=mock_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENG_ID}/reports/disagreement")

        breakdown = resp.json()["summary"]["type_breakdown"]
        assert breakdown["sequence_mismatch"] == 2
        assert breakdown["role_mismatch"] == 1


# ---------------------------------------------------------------------------
# Scenario 2: Consistency metrics include agreement rate
# ---------------------------------------------------------------------------


class TestScenario2ConsistencyMetrics:
    """BDD Scenario 2: Consistency metrics include agreement rate."""

    @pytest.mark.asyncio
    async def test_agreement_rate_computed(self):
        """Given 200 element pairs and 15 conflicts, agreement_rate = 92.5%."""
        session = _mock_session()

        # Mock responses for: total conflicts, resolved, open, latest model
        count_15 = MagicMock()
        count_15.scalar.return_value = 15

        count_5 = MagicMock()
        count_5.scalar.return_value = 5

        count_10 = MagicMock()
        count_10.scalar.return_value = 10

        model_mock = _make_process_model(element_count=200)
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model_mock

        session.execute = AsyncMock(side_effect=[count_15, count_5, count_10, model_result])

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENG_ID}/consistency-metrics")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_element_pairs"] == 200
        assert data["conflicting_pairs"] == 15
        assert data["agreement_rate"] == 92.5

    @pytest.mark.asyncio
    async def test_resolved_conflict_rate(self):
        """resolved_conflict_rate = resolved / total conflicts * 100."""
        session = _mock_session()

        count_10 = MagicMock()
        count_10.scalar.return_value = 10

        count_7 = MagicMock()
        count_7.scalar.return_value = 7

        count_3 = MagicMock()
        count_3.scalar.return_value = 3

        model_mock = _make_process_model(element_count=100)
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model_mock

        session.execute = AsyncMock(side_effect=[count_10, count_7, count_3, model_result])

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENG_ID}/consistency-metrics")

        data = resp.json()
        assert data["resolved_conflict_rate"] == 70.0

    @pytest.mark.asyncio
    async def test_open_conflict_count(self):
        """open_conflict_count returns count of unresolved + escalated."""
        session = _mock_session()

        count_total = MagicMock()
        count_total.scalar.return_value = 20

        count_resolved = MagicMock()
        count_resolved.scalar.return_value = 12

        count_open = MagicMock()
        count_open.scalar.return_value = 8

        model_mock = _make_process_model(element_count=100)
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model_mock

        session.execute = AsyncMock(side_effect=[count_total, count_resolved, count_open, model_result])

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENG_ID}/consistency-metrics")

        assert resp.json()["open_conflict_count"] == 8

    @pytest.mark.asyncio
    async def test_no_conflicts_100_percent_agreement(self):
        """With 0 conflicts, agreement_rate is 100%."""
        session = _mock_session()

        count_0 = MagicMock()
        count_0.scalar.return_value = 0

        model_mock = _make_process_model(element_count=50)
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model_mock

        session.execute = AsyncMock(side_effect=[count_0, count_0, count_0, model_result])

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENG_ID}/consistency-metrics")

        data = resp.json()
        assert data["agreement_rate"] == 100.0
        assert data["resolved_conflict_rate"] == 100.0


# ---------------------------------------------------------------------------
# Scenario 3: POV version trend shows conflict reduction rate
# ---------------------------------------------------------------------------


class TestScenario3PovTrend:
    """BDD Scenario 3: POV version trend shows conflict reduction rate."""

    @pytest.mark.asyncio
    async def test_trend_returns_chronological_entries(self):
        """Trend data returned in chronological order by POV version."""
        models = [
            _make_process_model(
                version=1,
                element_count=100,
                contradiction_count=20,
                generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            _make_process_model(
                version=2,
                element_count=120,
                contradiction_count=12,
                generated_at=datetime(2026, 2, 1, tzinfo=UTC),
            ),
        ]

        session = _mock_session()
        models_result = MagicMock()
        models_result.scalars.return_value.all.return_value = models

        session.execute = AsyncMock(return_value=models_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENG_ID}/consistency-metrics/trend")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["trend"]) == 2
        assert data["trend"][0]["pov_version"] == 1
        assert data["trend"][1]["pov_version"] == 2

    @pytest.mark.asyncio
    async def test_conflict_reduction_rate_computed(self):
        """Reduction rate between v1 (20 open) and v2 (12 open) = 40%."""
        models = [
            _make_process_model(
                version=1,
                element_count=100,
                contradiction_count=20,
                generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            _make_process_model(
                version=2,
                element_count=120,
                contradiction_count=12,
                generated_at=datetime(2026, 2, 1, tzinfo=UTC),
            ),
        ]

        session = _mock_session()
        models_result = MagicMock()
        models_result.scalars.return_value.all.return_value = models

        session.execute = AsyncMock(return_value=models_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENG_ID}/consistency-metrics/trend")

        data = resp.json()
        assert data["conflict_reduction_rate"] == 40.0

    @pytest.mark.asyncio
    async def test_each_trend_entry_has_required_fields(self):
        """Each entry includes pov_version, created_at, open/resolved counts, agreement_rate."""
        models = [
            _make_process_model(
                version=1,
                element_count=100,
                contradiction_count=5,
                generated_at=datetime(2026, 1, 15, tzinfo=UTC),
            ),
        ]

        session = _mock_session()
        models_result = MagicMock()
        models_result.scalars.return_value.all.return_value = models

        session.execute = AsyncMock(return_value=models_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENG_ID}/consistency-metrics/trend")

        entry = resp.json()["trend"][0]
        required = ["pov_version", "pov_created_at", "open_conflict_count", "resolved_conflict_count", "agreement_rate"]
        for field in required:
            assert field in entry, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_no_models_returns_empty_trend(self):
        """With no POV models, trend is empty."""
        session = _mock_session()
        models_result = MagicMock()
        models_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(return_value=models_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENG_ID}/consistency-metrics/trend")

        data = resp.json()
        assert data["trend"] == []
        assert data["conflict_reduction_rate"] is None

    @pytest.mark.asyncio
    async def test_snapshot_data_used_when_available(self):
        """When metadata_json has conflict_snapshot, use those counts."""
        models = [
            _make_process_model(
                version=1,
                element_count=100,
                contradiction_count=20,
                metadata_json={
                    "conflict_snapshot": {
                        "open_count": 18,
                        "resolved_count": 2,
                        "total_element_pairs": 200,
                    }
                },
                generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ]

        session = _mock_session()
        models_result = MagicMock()
        models_result.scalars.return_value.all.return_value = models

        session.execute = AsyncMock(return_value=models_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{ENG_ID}/consistency-metrics/trend")

        entry = resp.json()["trend"][0]
        assert entry["open_conflict_count"] == 18
        assert entry["resolved_conflict_count"] == 2
        # agreement: (200 - 20) / 200 = 90.0
        assert entry["agreement_rate"] == 90.0
