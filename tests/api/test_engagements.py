"""Comprehensive tests for the engagement management API.

Tests cover: create, list (with filters), get, update (PATCH),
archive (DELETE), dashboard, audit logs, and error cases.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.models import AuditAction, AuditLog, Engagement, EngagementStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_ENGAGEMENT = {
    "name": "P2P Assessment",
    "client": "Acme Corp",
    "business_area": "Procure-to-Pay",
    "description": "Assess P2P processes",
    "team": ["alice@acme.com", "bob@acme.com"],
}


def _make_engagement(**overrides) -> Engagement:  # noqa: ANN003
    """Create a test Engagement ORM object."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "P2P Assessment",
        "client": "Acme Corp",
        "business_area": "Procure-to-Pay",
        "description": "Assess P2P processes",
        "status": EngagementStatus.DRAFT,
        "team": ["alice@acme.com", "bob@acme.com"],
    }
    defaults.update(overrides)
    return Engagement(**defaults)


def _mock_scalar_result(value):  # noqa: ANN001, ANN202
    """Create a mock result that returns value from .scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalars_result(items: list) -> MagicMock:
    """Create a mock result whose .scalars().all() returns a list."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result = MagicMock()
    result.scalars.return_value = scalars_mock
    return result


def _mock_count_result(count: int) -> MagicMock:
    """Create a mock result whose .scalar() returns a count."""
    result = MagicMock()
    result.scalar.return_value = count
    return result


# ---------------------------------------------------------------------------
# Create endpoint
# ---------------------------------------------------------------------------


class TestCreateEngagement:
    """POST /api/v1/engagements/"""

    @pytest.mark.asyncio
    async def test_create_engagement(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should create engagement with team field and return 201."""
        response = await client.post("/api/v1/engagements/", json=VALID_ENGAGEMENT)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "P2P Assessment"
        assert data["client"] == "Acme Corp"
        assert data["team"] == ["alice@acme.com", "bob@acme.com"]
        assert data["status"] == "draft"

        # Verify session.add was called (once for engagement, once for audit)
        assert mock_db_session.add.call_count == 2
        mock_db_session.flush.assert_awaited_once()
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_engagement_with_active_status(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should allow specifying status at creation time."""
        payload = {**VALID_ENGAGEMENT, "status": "active"}
        response = await client.post("/api/v1/engagements/", json=payload)
        assert response.status_code == 201
        assert response.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_create_engagement_without_team(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Team should default to empty list when not provided."""
        payload = {
            "name": "No Team",
            "client": "Client B",
            "business_area": "Finance",
        }
        response = await client.post("/api/v1/engagements/", json=payload)
        assert response.status_code == 201
        assert response.json()["team"] == []

    @pytest.mark.asyncio
    async def test_create_engagement_validation_error(self, client: AsyncClient) -> None:
        """Should return 422 for invalid payload."""
        response = await client.post("/api/v1/engagements/", json={"name": ""})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_engagement_missing_required_fields(self, client: AsyncClient) -> None:
        """Should return 422 when required fields are missing."""
        response = await client.post("/api/v1/engagements/", json={})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# List endpoint with filters
# ---------------------------------------------------------------------------


class TestListEngagements:
    """GET /api/v1/engagements/"""

    @pytest.mark.asyncio
    async def test_list_engagements(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return paginated list of engagements."""
        eng1 = _make_engagement(name="Eng 1")
        eng2 = _make_engagement(name="Eng 2")

        mock_db_session.execute.side_effect = [
            _mock_scalars_result([eng1, eng2]),
            _mock_count_result(2),
        ]

        response = await client.get("/api/v1/engagements/")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_engagements_filter_by_status(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should filter by status query parameter."""
        eng = _make_engagement(status=EngagementStatus.ACTIVE)

        mock_db_session.execute.side_effect = [
            _mock_scalars_result([eng]),
            _mock_count_result(1),
        ]

        response = await client.get("/api/v1/engagements/?status_filter=active")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_list_engagements_filter_by_client(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should filter by client query parameter."""
        eng = _make_engagement(client="SpecificClient")

        mock_db_session.execute.side_effect = [
            _mock_scalars_result([eng]),
            _mock_count_result(1),
        ]

        response = await client.get("/api/v1/engagements/?client=SpecificClient")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["client"] == "SpecificClient"

    @pytest.mark.asyncio
    async def test_list_engagements_filter_by_business_area(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Should filter by business_area query parameter."""
        eng = _make_engagement(business_area="Order-to-Cash")

        mock_db_session.execute.side_effect = [
            _mock_scalars_result([eng]),
            _mock_count_result(1),
        ]

        response = await client.get("/api/v1/engagements/?business_area=Order-to-Cash")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["business_area"] == "Order-to-Cash"

    @pytest.mark.asyncio
    async def test_list_engagements_pagination(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should respect limit and offset parameters."""
        eng = _make_engagement(name="Page 2 Item")

        mock_db_session.execute.side_effect = [
            _mock_scalars_result([eng]),
            _mock_count_result(5),
        ]

        response = await client.get("/api/v1/engagements/?limit=1&offset=1")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_engagements_empty(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return empty list when no engagements exist."""
        mock_db_session.execute.side_effect = [
            _mock_scalars_result([]),
            _mock_count_result(0),
        ]

        response = await client.get("/api/v1/engagements/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []


# ---------------------------------------------------------------------------
# Get by ID
# ---------------------------------------------------------------------------


class TestGetEngagement:
    """GET /api/v1/engagements/{id}"""

    @pytest.mark.asyncio
    async def test_get_engagement_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return engagement when found."""
        eng = _make_engagement()
        mock_db_session.execute.return_value = _mock_scalar_result(eng)

        response = await client.get(f"/api/v1/engagements/{eng.id}")
        assert response.status_code == 200
        assert response.json()["name"] == "P2P Assessment"

    @pytest.mark.asyncio
    async def test_get_engagement_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 for non-existent engagement."""
        mock_db_session.execute.return_value = _mock_scalar_result(None)

        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/engagements/{fake_id}")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Update (PATCH)
# ---------------------------------------------------------------------------


class TestUpdateEngagement:
    """PATCH /api/v1/engagements/{id}"""

    @pytest.mark.asyncio
    async def test_update_engagement_name(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should update the name and create audit log."""
        eng = _make_engagement()
        mock_db_session.execute.return_value = _mock_scalar_result(eng)

        response = await client.patch(
            f"/api/v1/engagements/{eng.id}",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200

        # Verify the engagement was updated in-place
        assert eng.name == "Updated Name"
        # Verify audit log was added (session.add called for audit entry)
        assert mock_db_session.add.called
        mock_db_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_update_engagement_status(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should update status via PATCH."""
        eng = _make_engagement(status=EngagementStatus.DRAFT)
        mock_db_session.execute.return_value = _mock_scalar_result(eng)

        response = await client.patch(
            f"/api/v1/engagements/{eng.id}",
            json={"status": "active"},
        )
        assert response.status_code == 200
        assert eng.status == EngagementStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_update_engagement_team(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should update team list."""
        eng = _make_engagement(team=["old@example.com"])
        mock_db_session.execute.return_value = _mock_scalar_result(eng)

        response = await client.patch(
            f"/api/v1/engagements/{eng.id}",
            json={"team": ["new@example.com", "another@example.com"]},
        )
        assert response.status_code == 200
        assert eng.team == ["new@example.com", "another@example.com"]

    @pytest.mark.asyncio
    async def test_update_engagement_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 when engagement does not exist."""
        mock_db_session.execute.return_value = _mock_scalar_result(None)

        fake_id = uuid.uuid4()
        response = await client.patch(
            f"/api/v1/engagements/{fake_id}",
            json={"name": "Nope"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_engagement_empty_body(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 200 with no changes when body is empty."""
        eng = _make_engagement()
        mock_db_session.execute.return_value = _mock_scalar_result(eng)

        response = await client.patch(
            f"/api/v1/engagements/{eng.id}",
            json={},
        )
        assert response.status_code == 200
        # No audit log should be created for empty update
        assert not mock_db_session.add.called

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should update multiple fields at once."""
        eng = _make_engagement()
        mock_db_session.execute.return_value = _mock_scalar_result(eng)

        response = await client.patch(
            f"/api/v1/engagements/{eng.id}",
            json={"name": "New Name", "client": "New Client", "description": "New desc"},
        )
        assert response.status_code == 200
        assert eng.name == "New Name"
        assert eng.client == "New Client"
        assert eng.description == "New desc"


# ---------------------------------------------------------------------------
# Archive (DELETE)
# ---------------------------------------------------------------------------


class TestArchiveEngagement:
    """PATCH /api/v1/engagements/{id}/archive"""

    @pytest.mark.asyncio
    async def test_archive_engagement(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should soft-delete by setting status to ARCHIVED."""
        eng = _make_engagement(status=EngagementStatus.ACTIVE)
        mock_db_session.execute.return_value = _mock_scalar_result(eng)

        response = await client.patch(f"/api/v1/engagements/{eng.id}/archive")
        assert response.status_code == 200
        assert eng.status == EngagementStatus.ARCHIVED

        # Verify audit log was added
        assert mock_db_session.add.called
        mock_db_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_archive_engagement_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 when engagement does not exist."""
        mock_db_session.execute.return_value = _mock_scalar_result(None)

        fake_id = uuid.uuid4()
        response = await client.patch(f"/api/v1/engagements/{fake_id}/archive")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_archive_already_archived(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should succeed even if already archived (idempotent)."""
        eng = _make_engagement(status=EngagementStatus.ARCHIVED)
        mock_db_session.execute.return_value = _mock_scalar_result(eng)

        response = await client.patch(f"/api/v1/engagements/{eng.id}/archive")
        assert response.status_code == 200
        assert eng.status == EngagementStatus.ARCHIVED


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class TestDashboard:
    """GET /api/v1/engagements/{id}/dashboard"""

    @pytest.mark.asyncio
    async def test_dashboard_no_evidence(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return dashboard with zero evidence."""
        eng = _make_engagement()

        # 1st call: get engagement (scalar_one_or_none)
        # 2nd call: count evidence (scalar)
        # 3rd call: count by category (iterate rows)
        cat_result = MagicMock()
        cat_result.__iter__ = MagicMock(return_value=iter([]))

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(eng),
            _mock_count_result(0),
            cat_result,
        ]

        response = await client.get(f"/api/v1/engagements/{eng.id}/dashboard")
        assert response.status_code == 200

        data = response.json()
        assert data["evidence_count"] == 0
        assert data["evidence_by_category"] == {}
        assert data["coverage_percentage"] == 0.0
        assert data["engagement"]["name"] == "P2P Assessment"

    @pytest.mark.asyncio
    async def test_dashboard_with_evidence(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return evidence counts and coverage."""
        eng = _make_engagement()

        # Mock category results as named tuples
        cat_row_1 = MagicMock()
        cat_row_1.category = "documents"
        cat_row_1.count = 5
        cat_row_2 = MagicMock()
        cat_row_2.category = "images"
        cat_row_2.count = 3

        # Category query: iterate over rows directly
        cat_result = MagicMock()
        cat_result.__iter__ = MagicMock(return_value=iter([cat_row_1, cat_row_2]))

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(eng),
            _mock_count_result(8),
            cat_result,
        ]

        response = await client.get(f"/api/v1/engagements/{eng.id}/dashboard")
        assert response.status_code == 200

        data = response.json()
        assert data["evidence_count"] == 8
        assert data["evidence_by_category"]["documents"] == 5
        assert data["evidence_by_category"]["images"] == 3
        # 2 out of 12 categories = 16.67%
        assert abs(data["coverage_percentage"] - 16.67) < 0.01

    @pytest.mark.asyncio
    async def test_dashboard_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 when engagement does not exist."""
        mock_db_session.execute.return_value = _mock_scalar_result(None)

        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/engagements/{fake_id}/dashboard")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------


class TestAuditLogs:
    """GET /api/v1/engagements/{id}/audit-logs"""

    @pytest.mark.asyncio
    async def test_get_audit_logs(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return audit log entries for an engagement."""
        eng = _make_engagement()
        log1 = AuditLog(
            id=uuid.uuid4(),
            engagement_id=eng.id,
            action=AuditAction.ENGAGEMENT_CREATED,
            actor="system",
            details='{"name": "P2P Assessment"}',
        )

        # 1st call: verify engagement exists
        # 2nd call: fetch audit logs
        mock_db_session.execute.side_effect = [
            _mock_scalar_result(eng),
            _mock_scalars_result([log1]),
        ]

        response = await client.get(f"/api/v1/engagements/{eng.id}/audit-logs")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["action"] == "engagement_created"
        assert data[0]["actor"] == "system"

    @pytest.mark.asyncio
    async def test_audit_logs_empty(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return empty list when no audit logs exist."""
        eng = _make_engagement()

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(eng),
            _mock_scalars_result([]),
        ]

        response = await client.get(f"/api/v1/engagements/{eng.id}/audit-logs")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_audit_logs_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 when engagement does not exist."""
        mock_db_session.execute.return_value = _mock_scalar_result(None)

        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/engagements/{fake_id}/audit-logs")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Audit Log Creation Verification
# ---------------------------------------------------------------------------


class TestAuditLogCreation:
    """Verify that mutation operations create audit log entries."""

    @pytest.mark.asyncio
    async def test_create_generates_audit_log(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """POST should add both engagement and audit log to session."""
        response = await client.post("/api/v1/engagements/", json=VALID_ENGAGEMENT)
        assert response.status_code == 201

        # session.add called twice: once for engagement, once for audit log
        add_calls = mock_db_session.add.call_args_list
        assert len(add_calls) == 2

        # First add is the Engagement
        first_added = add_calls[0][0][0]
        assert isinstance(first_added, Engagement)

        # Second add is the AuditLog
        second_added = add_calls[1][0][0]
        assert isinstance(second_added, AuditLog)
        assert second_added.action == AuditAction.ENGAGEMENT_CREATED

    @pytest.mark.asyncio
    async def test_update_generates_audit_log(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """PATCH with changes should create an ENGAGEMENT_UPDATED audit entry."""
        eng = _make_engagement()
        mock_db_session.execute.return_value = _mock_scalar_result(eng)

        response = await client.patch(
            f"/api/v1/engagements/{eng.id}",
            json={"name": "Changed Name"},
        )
        assert response.status_code == 200

        add_calls = mock_db_session.add.call_args_list
        assert len(add_calls) == 1
        audit = add_calls[0][0][0]
        assert isinstance(audit, AuditLog)
        assert audit.action == AuditAction.ENGAGEMENT_UPDATED

    @pytest.mark.asyncio
    async def test_archive_generates_audit_log(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """PATCH /archive should create an ENGAGEMENT_ARCHIVED audit entry."""
        eng = _make_engagement(status=EngagementStatus.ACTIVE)
        mock_db_session.execute.return_value = _mock_scalar_result(eng)

        response = await client.patch(f"/api/v1/engagements/{eng.id}/archive")
        assert response.status_code == 200

        add_calls = mock_db_session.add.call_args_list
        assert len(add_calls) == 1
        audit = add_calls[0][0][0]
        assert isinstance(audit, AuditLog)
        assert audit.action == AuditAction.ENGAGEMENT_ARCHIVED
