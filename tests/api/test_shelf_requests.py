"""Tests for the shelf data request management API.

Tests cover: create, list, get, status, update, intake.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.models import (
    EvidenceCategory,
    EvidenceItem,
    ShelfDataRequest,
    ShelfDataRequestItem,
    ShelfRequestItemPriority,
    ShelfRequestItemStatus,
    ShelfRequestStatus,
    ValidationStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_shelf_request(**overrides) -> ShelfDataRequest:  # noqa: ANN003
    """Create a test ShelfDataRequest ORM object."""
    defaults = {
        "id": uuid.uuid4(),
        "engagement_id": uuid.uuid4(),
        "title": "P2P Evidence Request",
        "description": "Gather all P2P process documentation",
        "status": ShelfRequestStatus.DRAFT,
    }
    defaults.update(overrides)
    req = ShelfDataRequest(**defaults)
    # Initialize items relationship
    if "items" not in overrides:
        req.items = []
    return req


def _make_shelf_item(**overrides) -> ShelfDataRequestItem:  # noqa: ANN003
    """Create a test ShelfDataRequestItem ORM object."""
    defaults = {
        "id": uuid.uuid4(),
        "request_id": uuid.uuid4(),
        "category": EvidenceCategory.DOCUMENTS,
        "item_name": "Process Map",
        "description": "Current state P2P process map",
        "priority": ShelfRequestItemPriority.HIGH,
        "status": ShelfRequestItemStatus.PENDING,
        "matched_evidence_id": None,
    }
    defaults.update(overrides)
    return ShelfDataRequestItem(**defaults)


def _make_evidence(**overrides) -> EvidenceItem:  # noqa: ANN003
    """Create a test EvidenceItem ORM object."""
    defaults = {
        "id": uuid.uuid4(),
        "engagement_id": uuid.uuid4(),
        "name": "test.pdf",
        "category": EvidenceCategory.DOCUMENTS,
        "format": "pdf",
        "content_hash": "abc123def456" * 5 + "abcd",
        "validation_status": ValidationStatus.PENDING,
        "completeness_score": 0.0,
        "reliability_score": 0.0,
        "freshness_score": 0.0,
        "consistency_score": 0.0,
    }
    defaults.update(overrides)
    return EvidenceItem(**defaults)


def _mock_scalar_result(value):  # noqa: ANN001, ANN202
    """Create a mock result that returns value from .scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalars_unique_result(items: list) -> MagicMock:
    """Create a mock result whose .scalars().unique().all() returns a list."""
    unique_mock = MagicMock()
    unique_mock.all.return_value = items
    scalars_mock = MagicMock()
    scalars_mock.unique.return_value = unique_mock
    result = MagicMock()
    result.scalars.return_value = scalars_mock
    return result


def _mock_count_result(count: int) -> MagicMock:
    """Create a mock result whose .scalar() returns a count."""
    result = MagicMock()
    result.scalar.return_value = count
    return result


# ---------------------------------------------------------------------------
# Create Shelf Request
# ---------------------------------------------------------------------------


class TestCreateShelfRequest:
    """POST /api/v1/shelf-requests/"""

    @pytest.mark.asyncio
    async def test_create_shelf_request(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should create a shelf request with items."""
        engagement_id = uuid.uuid4()
        req = _make_shelf_request(engagement_id=engagement_id)
        req.items = [
            _make_shelf_item(request_id=req.id, category=EvidenceCategory.DOCUMENTS, item_name="Process Map"),
        ]

        # After commit, the re-fetch with selectinload returns the request
        mock_db_session.execute.return_value = _mock_scalar_result(req)

        response = await client.post(
            "/api/v1/shelf-requests/",
            json={
                "engagement_id": str(engagement_id),
                "title": "P2P Evidence Request",
                "items": [
                    {
                        "category": "documents",
                        "item_name": "Process Map",
                        "priority": "high",
                    }
                ],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "P2P Evidence Request"
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_create_shelf_request_empty_items(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should create a shelf request with no items."""
        engagement_id = uuid.uuid4()
        req = _make_shelf_request(engagement_id=engagement_id, title="Empty Request")
        req.items = []

        mock_db_session.execute.return_value = _mock_scalar_result(req)

        response = await client.post(
            "/api/v1/shelf-requests/",
            json={
                "engagement_id": str(engagement_id),
                "title": "Empty Request",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Empty Request"
        assert len(data["items"]) == 0


# ---------------------------------------------------------------------------
# List Shelf Requests
# ---------------------------------------------------------------------------


class TestListShelfRequests:
    """GET /api/v1/shelf-requests/"""

    @pytest.mark.asyncio
    async def test_list_shelf_requests(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return paginated list."""
        req1 = _make_shelf_request(title="Request 1")
        req2 = _make_shelf_request(title="Request 2")

        mock_db_session.execute.side_effect = [
            _mock_scalars_unique_result([req1, req2]),
            _mock_count_result(2),
        ]

        response = await client.get("/api/v1/shelf-requests/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_shelf_requests_empty(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return empty list when no requests exist."""
        mock_db_session.execute.side_effect = [
            _mock_scalars_unique_result([]),
            _mock_count_result(0),
        ]

        response = await client.get("/api/v1/shelf-requests/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []


# ---------------------------------------------------------------------------
# Get Shelf Request
# ---------------------------------------------------------------------------


class TestGetShelfRequest:
    """GET /api/v1/shelf-requests/{id}"""

    @pytest.mark.asyncio
    async def test_get_shelf_request(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return shelf request with items."""
        req = _make_shelf_request()
        req.items = [_make_shelf_item(request_id=req.id)]

        mock_db_session.execute.return_value = _mock_scalar_result(req)

        response = await client.get(f"/api/v1/shelf-requests/{req.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "P2P Evidence Request"

    @pytest.mark.asyncio
    async def test_get_shelf_request_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 for non-existent request."""
        mock_db_session.execute.return_value = _mock_scalar_result(None)

        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/shelf-requests/{fake_id}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Get Shelf Request Status
# ---------------------------------------------------------------------------


class TestGetShelfRequestStatus:
    """GET /api/v1/shelf-requests/{id}/status"""

    @pytest.mark.asyncio
    async def test_get_status_with_items(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return fulfillment status breakdown."""
        req = _make_shelf_request()
        req.items = [
            _make_shelf_item(request_id=req.id, status=ShelfRequestItemStatus.RECEIVED),
            _make_shelf_item(request_id=req.id, status=ShelfRequestItemStatus.PENDING),
            _make_shelf_item(request_id=req.id, status=ShelfRequestItemStatus.OVERDUE),
        ]

        mock_db_session.execute.return_value = _mock_scalar_result(req)

        response = await client.get(f"/api/v1/shelf-requests/{req.id}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["total_items"] == 3
        assert data["received_items"] == 1
        assert data["pending_items"] == 1
        assert data["overdue_items"] == 1
        assert abs(data["fulfillment_percentage"] - 33.33) < 0.1

    @pytest.mark.asyncio
    async def test_get_status_no_items(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 0% fulfillment when no items."""
        req = _make_shelf_request()
        req.items = []

        mock_db_session.execute.return_value = _mock_scalar_result(req)

        response = await client.get(f"/api/v1/shelf-requests/{req.id}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["total_items"] == 0
        assert data["fulfillment_percentage"] == 0.0


# ---------------------------------------------------------------------------
# Update Shelf Request
# ---------------------------------------------------------------------------


class TestUpdateShelfRequest:
    """PATCH /api/v1/shelf-requests/{id}"""

    @pytest.mark.asyncio
    async def test_update_shelf_request_status(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should update status to SENT."""
        req = _make_shelf_request(status=ShelfRequestStatus.DRAFT)

        # First call: initial fetch, second call: re-fetch after update
        mock_db_session.execute.side_effect = [
            _mock_scalar_result(req),
            _mock_scalar_result(req),
        ]

        response = await client.patch(
            f"/api/v1/shelf-requests/{req.id}",
            json={"status": "sent"},
        )
        assert response.status_code == 200
        assert req.status == ShelfRequestStatus.SENT

    @pytest.mark.asyncio
    async def test_update_shelf_request_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 for non-existent request."""
        mock_db_session.execute.return_value = _mock_scalar_result(None)

        fake_id = uuid.uuid4()
        response = await client.patch(
            f"/api/v1/shelf-requests/{fake_id}",
            json={"title": "Updated"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_shelf_request_empty_body(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return request unchanged when body is empty."""
        req = _make_shelf_request()
        mock_db_session.execute.return_value = _mock_scalar_result(req)

        response = await client.patch(
            f"/api/v1/shelf-requests/{req.id}",
            json={},
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Intake (Client Evidence Submission)
# ---------------------------------------------------------------------------


class TestIntake:
    """POST /api/v1/shelf-requests/{id}/intake"""

    @pytest.mark.asyncio
    async def test_intake_direct_match(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should match evidence to specific item when item_id provided."""
        req = _make_shelf_request()
        item = _make_shelf_item(request_id=req.id, category=EvidenceCategory.DOCUMENTS)
        req.items = [item]

        ev = _make_evidence(category=EvidenceCategory.DOCUMENTS)

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(req),  # shelf request
            _mock_scalar_result(ev),  # evidence item
        ]

        response = await client.post(
            f"/api/v1/shelf-requests/{req.id}/intake",
            json={
                "evidence_id": str(ev.id),
                "item_id": str(item.id),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["matched_item_id"] == str(item.id)
        assert data["auto_matched"] is False

    @pytest.mark.asyncio
    async def test_intake_auto_match_by_category(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should auto-match evidence by category when item_id not provided."""
        req = _make_shelf_request()
        item = _make_shelf_item(
            request_id=req.id,
            category=EvidenceCategory.DOCUMENTS,
            status=ShelfRequestItemStatus.PENDING,
        )
        req.items = [item]

        ev = _make_evidence(category=EvidenceCategory.DOCUMENTS)

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(req),
            _mock_scalar_result(ev),
        ]

        response = await client.post(
            f"/api/v1/shelf-requests/{req.id}/intake",
            json={"evidence_id": str(ev.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["matched_item_id"] == str(item.id)
        assert data["auto_matched"] is True

    @pytest.mark.asyncio
    async def test_intake_no_match(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should handle no match gracefully."""
        req = _make_shelf_request()
        item = _make_shelf_item(
            request_id=req.id,
            category=EvidenceCategory.IMAGES,  # Different category
            status=ShelfRequestItemStatus.PENDING,
        )
        req.items = [item]

        ev = _make_evidence(name="unrelated.pdf", category=EvidenceCategory.DOCUMENTS)

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(req),
            _mock_scalar_result(ev),
        ]

        response = await client.post(
            f"/api/v1/shelf-requests/{req.id}/intake",
            json={"evidence_id": str(ev.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["matched_item_id"] is None

    @pytest.mark.asyncio
    async def test_intake_evidence_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 when evidence does not exist."""
        req = _make_shelf_request()
        req.items = []

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(req),
            _mock_scalar_result(None),  # Evidence not found
        ]

        fake_ev_id = uuid.uuid4()
        response = await client.post(
            f"/api/v1/shelf-requests/{req.id}/intake",
            json={"evidence_id": str(fake_ev_id)},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_intake_request_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 when shelf request does not exist."""
        mock_db_session.execute.return_value = _mock_scalar_result(None)

        fake_id = uuid.uuid4()
        fake_ev_id = uuid.uuid4()
        response = await client.post(
            f"/api/v1/shelf-requests/{fake_id}/intake",
            json={"evidence_id": str(fake_ev_id)},
        )
        assert response.status_code == 404
