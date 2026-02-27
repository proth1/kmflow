"""BDD tests for Story #388: Disagreement Resolution Workflow.

Covers three acceptance scenarios:
  1. Overdue conflicts appear in escalation queue
  2. SME resolves conflict with resolution recorded
  3. Disagreement report returns all conflicts filterable by type/severity/status
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.routes.conflicts import ESCALATION_THRESHOLD_HOURS, router
from src.core.models.conflict import ConflictObject, MismatchType, ResolutionStatus, ResolutionType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SYSTEM_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _make_conflict(
    *,
    engagement_id: uuid.UUID | None = None,
    mismatch_type: MismatchType = MismatchType.SEQUENCE_MISMATCH,
    resolution_status: ResolutionStatus = ResolutionStatus.UNRESOLVED,
    severity: float = 0.5,
    escalation_flag: bool = False,
    assigned_to: uuid.UUID | None = None,
    resolver_id: uuid.UUID | None = None,
    resolution_type: ResolutionType | None = None,
    created_at: datetime | None = None,
    resolved_at: datetime | None = None,
) -> MagicMock:
    """Create a mock ConflictObject."""
    obj = MagicMock(spec=ConflictObject)
    obj.id = uuid.uuid4()
    obj.engagement_id = engagement_id or uuid.uuid4()
    obj.mismatch_type = mismatch_type
    obj.resolution_type = resolution_type
    obj.resolution_status = resolution_status
    obj.source_a_id = uuid.uuid4()
    obj.source_b_id = uuid.uuid4()
    obj.severity = severity
    obj.escalation_flag = escalation_flag
    obj.resolution_notes = None
    obj.conflict_detail = None
    obj.resolution_details = None
    obj.resolver_id = resolver_id
    obj.assigned_to = assigned_to
    obj.created_at = created_at or datetime.now(UTC)
    obj.resolved_at = resolved_at
    return obj


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Scenario 1: Overdue conflicts appear in escalation queue
# ---------------------------------------------------------------------------


class TestScenario1EscalationQueue:
    """BDD Scenario 1: Overdue conflicts appear in escalation queue."""

    @pytest.mark.asyncio
    async def test_overdue_conflicts_are_escalated(self):
        """Given a ConflictObject with status=open created >48h ago and unassigned,
        When the escalation check runs,
        Then it is marked as escalated."""
        engagement_id = uuid.uuid4()
        old_conflict = _make_conflict(
            engagement_id=engagement_id,
            created_at=datetime.now(UTC) - timedelta(hours=72),
        )

        session = _mock_session()
        # escalation check query returns the overdue conflict
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [old_conflict]
        session.execute = AsyncMock(return_value=mock_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/conflicts/escalation-check")

        assert resp.status_code == 200
        data = resp.json()
        assert data["escalated_count"] == 1
        assert old_conflict.escalation_flag is True
        assert old_conflict.resolution_status == ResolutionStatus.ESCALATED

    @pytest.mark.asyncio
    async def test_no_overdue_conflicts_returns_zero(self):
        """When no conflicts are overdue, escalation check returns 0."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/conflicts/escalation-check")

        assert resp.status_code == 200
        assert resp.json()["escalated_count"] == 0

    @pytest.mark.asyncio
    async def test_escalation_writes_audit_entry(self):
        """Escalation creates an audit log entry for each escalated conflict."""
        old_conflict = _make_conflict(
            created_at=datetime.now(UTC) - timedelta(hours=50),
        )

        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [old_conflict]
        session.execute = AsyncMock(return_value=mock_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/conflicts/escalation-check")

        # session.add called for audit entry
        assert session.add.call_count >= 1

    @pytest.mark.asyncio
    async def test_escalated_conflicts_filterable_by_flag(self):
        """GET /api/v1/engagements/{id}/conflicts?escalated=true returns escalated."""
        eng_id = uuid.uuid4()
        escalated = _make_conflict(engagement_id=eng_id, escalation_flag=True, severity=0.8)

        session = _mock_session()
        # First call: count, second call: rows
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [escalated]
        session.execute = AsyncMock(side_effect=[count_result, rows_result])

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{eng_id}/conflicts?escalated=true")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["escalation_flag"] is True

    @pytest.mark.asyncio
    async def test_custom_threshold_hours(self):
        """Escalation check accepts custom threshold_hours parameter."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/conflicts/escalation-check?threshold_hours=24")

        assert resp.status_code == 200
        assert resp.json()["threshold_hours"] == 24


# ---------------------------------------------------------------------------
# Scenario 2: SME resolves conflict with resolution recorded
# ---------------------------------------------------------------------------


class TestScenario2ConflictResolution:
    """BDD Scenario 2: SME resolves conflict with resolution recorded."""

    @pytest.mark.asyncio
    async def test_resolve_conflict_success(self):
        """Given an open ConflictObject assigned to an SME,
        When PATCH /api/v1/conflicts/{id}/resolve is called,
        Then status=resolved, resolution_type and resolver_id are persisted."""
        conflict = _make_conflict(
            resolution_status=ResolutionStatus.UNRESOLVED,
            assigned_to=uuid.uuid4(),
        )
        resolver = uuid.uuid4()

        session = _mock_session()
        fetch_result = MagicMock()
        fetch_result.scalar_one_or_none.return_value = conflict
        session.execute = AsyncMock(return_value=fetch_result)
        session.refresh = AsyncMock()

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        payload = {
            "resolution_type": "naming_variant",
            "resolution_notes": "Same process, different label",
            "resolver_id": str(resolver),
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(f"/api/v1/conflicts/{conflict.id}/resolve", json=payload)

        assert resp.status_code == 200
        assert conflict.resolution_status == ResolutionStatus.RESOLVED
        assert conflict.resolution_type == ResolutionType.NAMING_VARIANT
        assert conflict.resolver_id == resolver
        assert conflict.resolved_at is not None

    @pytest.mark.asyncio
    async def test_resolve_writes_audit_entry(self):
        """Resolution action writes an immutable audit log entry."""
        conflict = _make_conflict(resolution_status=ResolutionStatus.UNRESOLVED)
        resolver = uuid.uuid4()

        session = _mock_session()
        fetch_result = MagicMock()
        fetch_result.scalar_one_or_none.return_value = conflict
        session.execute = AsyncMock(return_value=fetch_result)
        session.refresh = AsyncMock()

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        payload = {
            "resolution_type": "genuine_disagreement",
            "resolution_notes": "Process owners disagree on sequence",
            "resolver_id": str(resolver),
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.patch(f"/api/v1/conflicts/{conflict.id}/resolve", json=payload)

        # Audit entry added to session
        assert session.add.call_count >= 1

    @pytest.mark.asyncio
    async def test_resolve_already_resolved_returns_409(self):
        """Resolving an already-resolved conflict returns 409 Conflict."""
        conflict = _make_conflict(resolution_status=ResolutionStatus.RESOLVED)

        session = _mock_session()
        fetch_result = MagicMock()
        fetch_result.scalar_one_or_none.return_value = conflict
        session.execute = AsyncMock(return_value=fetch_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        payload = {
            "resolution_type": "naming_variant",
            "resolver_id": str(uuid.uuid4()),
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(f"/api/v1/conflicts/{conflict.id}/resolve", json=payload)

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_returns_404(self):
        """Resolving a nonexistent conflict returns 404."""
        session = _mock_session()
        fetch_result = MagicMock()
        fetch_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=fetch_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        payload = {
            "resolution_type": "temporal_shift",
            "resolver_id": str(uuid.uuid4()),
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(f"/api/v1/conflicts/{uuid.uuid4()}/resolve", json=payload)

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_assign_conflict_success(self):
        """Assigning a conflict to an SME succeeds."""
        conflict = _make_conflict(resolution_status=ResolutionStatus.UNRESOLVED)
        sme_id = uuid.uuid4()

        session = _mock_session()
        fetch_result = MagicMock()
        fetch_result.scalar_one_or_none.return_value = conflict
        session.execute = AsyncMock(return_value=fetch_result)
        session.refresh = AsyncMock()

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                f"/api/v1/conflicts/{conflict.id}/assign",
                json={"assigned_to": str(sme_id)},
            )

        assert resp.status_code == 200
        assert conflict.assigned_to == sme_id


# ---------------------------------------------------------------------------
# Scenario 3: Disagreement report returns all conflicts filterable
# ---------------------------------------------------------------------------


class TestScenario3DisagreementReport:
    """BDD Scenario 3: Disagreement report returns all conflicts filterable."""

    @pytest.mark.asyncio
    async def test_unfiltered_returns_all(self):
        """Given 15 conflicts, unfiltered call returns all 15."""
        eng_id = uuid.uuid4()
        conflicts = [_make_conflict(engagement_id=eng_id, severity=0.1 * i) for i in range(15)]

        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar.return_value = 15
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = conflicts
        session.execute = AsyncMock(side_effect=[count_result, rows_result])

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{eng_id}/conflicts?limit=100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 15
        assert len(data["items"]) == 15

    @pytest.mark.asyncio
    async def test_filter_by_mismatch_type(self):
        """Filter by mismatch_type returns only matching conflicts."""
        eng_id = uuid.uuid4()
        role_conflict = _make_conflict(
            engagement_id=eng_id,
            mismatch_type=MismatchType.ROLE_MISMATCH,
        )

        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [role_conflict]
        session.execute = AsyncMock(side_effect=[count_result, rows_result])

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{eng_id}/conflicts?mismatch_type=role_mismatch")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_filter_by_resolution_status(self):
        """Filter by resolution_status returns only matching conflicts."""
        eng_id = uuid.uuid4()
        resolved = _make_conflict(
            engagement_id=eng_id,
            resolution_status=ResolutionStatus.RESOLVED,
            resolution_type=ResolutionType.NAMING_VARIANT,
            resolver_id=uuid.uuid4(),
            resolved_at=datetime.now(UTC),
        )

        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [resolved]
        session.execute = AsyncMock(side_effect=[count_result, rows_result])

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{eng_id}/conflicts?resolution_status=resolved")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"][0]["resolution_type"] == "naming_variant"
        assert data["items"][0]["resolver_id"] is not None

    @pytest.mark.asyncio
    async def test_filter_by_severity_range(self):
        """Filter by severity_min and severity_max."""
        eng_id = uuid.uuid4()
        high = _make_conflict(engagement_id=eng_id, severity=0.9)

        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [high]
        session.execute = AsyncMock(side_effect=[count_result, rows_result])

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{eng_id}/conflicts?severity_min=0.7&severity_max=1.0")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_pagination_limit_offset(self):
        """Pagination returns correct limit and offset."""
        eng_id = uuid.uuid4()
        page = [_make_conflict(engagement_id=eng_id) for _ in range(5)]

        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar.return_value = 15
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = page
        session.execute = AsyncMock(side_effect=[count_result, rows_result])

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{eng_id}/conflicts?limit=5&offset=5")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 15
        assert data["limit"] == 5
        assert data["offset"] == 5
        assert len(data["items"]) == 5

    @pytest.mark.asyncio
    async def test_response_includes_all_fields(self):
        """Each conflict in response includes all required fields."""
        eng_id = uuid.uuid4()
        conflict = _make_conflict(
            engagement_id=eng_id,
            resolution_status=ResolutionStatus.RESOLVED,
            resolution_type=ResolutionType.TEMPORAL_SHIFT,
            resolver_id=uuid.uuid4(),
            resolved_at=datetime.now(UTC),
        )
        conflict.conflict_detail = {"description": "Timing difference"}
        conflict.resolution_details = {"method": "manual"}

        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [conflict]
        session.execute = AsyncMock(side_effect=[count_result, rows_result])

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{eng_id}/conflicts")

        data = resp.json()["items"][0]
        required_fields = [
            "id",
            "mismatch_type",
            "severity",
            "resolution_status",
            "resolution_type",
            "resolver_id",
            "source_a_id",
            "source_b_id",
            "conflict_detail",
            "resolution_details",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_filter_by_assigned_to(self):
        """Filter by assigned_to returns only SME's assigned conflicts."""
        eng_id = uuid.uuid4()
        sme_id = uuid.uuid4()
        conflict = _make_conflict(engagement_id=eng_id, assigned_to=sme_id)

        session = _mock_session()
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [conflict]
        session.execute = AsyncMock(side_effect=[count_result, rows_result])

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/engagements/{eng_id}/conflicts?assigned_to={sme_id}")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for conflict resolution workflow."""

    @pytest.mark.asyncio
    async def test_escalate_conflict_manually(self):
        """Manual escalation sets flag and writes audit."""
        conflict = _make_conflict(resolution_status=ResolutionStatus.UNRESOLVED)

        session = _mock_session()
        fetch_result = MagicMock()
        fetch_result.scalar_one_or_none.return_value = conflict
        session.execute = AsyncMock(return_value=fetch_result)
        session.refresh = AsyncMock()

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                f"/api/v1/conflicts/{conflict.id}/escalate",
                json={"escalation_notes": "Needs leadership review"},
            )

        assert resp.status_code == 200
        assert conflict.escalation_flag is True
        assert conflict.resolution_status == ResolutionStatus.ESCALATED

    @pytest.mark.asyncio
    async def test_escalate_resolved_returns_409(self):
        """Cannot escalate an already-resolved conflict."""
        conflict = _make_conflict(resolution_status=ResolutionStatus.RESOLVED)

        session = _mock_session()
        fetch_result = MagicMock()
        fetch_result.scalar_one_or_none.return_value = conflict
        session.execute = AsyncMock(return_value=fetch_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                f"/api/v1/conflicts/{conflict.id}/escalate",
                json={},
            )

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_assign_resolved_conflict_returns_409(self):
        """Cannot assign a resolved conflict to an SME."""
        conflict = _make_conflict(resolution_status=ResolutionStatus.RESOLVED)

        session = _mock_session()
        fetch_result = MagicMock()
        fetch_result.scalar_one_or_none.return_value = conflict
        session.execute = AsyncMock(return_value=fetch_result)

        app = _make_app()
        app.dependency_overrides[__import__("src.api.deps", fromlist=["get_session"]).get_session] = lambda: session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                f"/api/v1/conflicts/{conflict.id}/assign",
                json={"assigned_to": str(uuid.uuid4())},
            )

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_default_escalation_threshold(self):
        """Default escalation threshold is 48 hours."""
        assert ESCALATION_THRESHOLD_HOURS == 48
