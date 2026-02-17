"""Tests for the evidence management API.

Tests cover: upload, get, list, validate, batch validate, fragments.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.models import (
    EvidenceCategory,
    EvidenceFragment,
    EvidenceItem,
    FragmentType,
    ValidationStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_evidence(**overrides) -> EvidenceItem:  # noqa: ANN003
    """Create a test EvidenceItem ORM object."""
    defaults = {
        "id": uuid.uuid4(),
        "engagement_id": uuid.uuid4(),
        "name": "test.pdf",
        "category": EvidenceCategory.DOCUMENTS,
        "format": "pdf",
        "content_hash": "abc123" * 10 + "abcd",
        "file_path": "/evidence_store/test.pdf",
        "size_bytes": 1024,
        "mime_type": "application/pdf",
        "metadata_json": None,
        "source_date": None,
        "completeness_score": 0.5,
        "reliability_score": 0.6,
        "freshness_score": 0.7,
        "consistency_score": 0.8,
        "duplicate_of_id": None,
        "validation_status": ValidationStatus.PENDING,
    }
    defaults.update(overrides)
    return EvidenceItem(**defaults)


def _make_fragment(**overrides) -> EvidenceFragment:  # noqa: ANN003
    """Create a test EvidenceFragment ORM object."""
    defaults = {
        "id": uuid.uuid4(),
        "evidence_id": uuid.uuid4(),
        "fragment_type": FragmentType.TEXT,
        "content": "Sample text content",
        "metadata_json": None,
    }
    defaults.update(overrides)
    return EvidenceFragment(**defaults)


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
# Get Evidence
# ---------------------------------------------------------------------------


class TestGetEvidence:
    """GET /api/v1/evidence/{id}"""

    @pytest.mark.asyncio
    async def test_get_evidence_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return evidence with fragment count."""
        ev = _make_evidence()
        mock_db_session.execute.side_effect = [
            _mock_scalar_result(ev),
            _mock_count_result(5),
        ]

        response = await client.get(f"/api/v1/evidence/{ev.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test.pdf"
        assert data["fragment_count"] == 5

    @pytest.mark.asyncio
    async def test_get_evidence_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 for non-existent evidence."""
        mock_db_session.execute.return_value = _mock_scalar_result(None)

        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/evidence/{fake_id}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# List Evidence
# ---------------------------------------------------------------------------


class TestListEvidence:
    """GET /api/v1/evidence/"""

    @pytest.mark.asyncio
    async def test_list_evidence(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return paginated list."""
        ev1 = _make_evidence(name="file1.pdf")
        ev2 = _make_evidence(name="file2.csv")

        mock_db_session.execute.side_effect = [
            _mock_scalars_result([ev1, ev2]),
            _mock_count_result(2),
        ]

        response = await client.get("/api/v1/evidence/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_evidence_filter_by_category(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should filter by category."""
        ev = _make_evidence(category=EvidenceCategory.STRUCTURED_DATA)

        mock_db_session.execute.side_effect = [
            _mock_scalars_result([ev]),
            _mock_count_result(1),
        ]

        response = await client.get("/api/v1/evidence/?category=structured_data")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_evidence_empty(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return empty list when no evidence."""
        mock_db_session.execute.side_effect = [
            _mock_scalars_result([]),
            _mock_count_result(0),
        ]

        response = await client.get("/api/v1/evidence/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------


class TestValidateEvidence:
    """PATCH /api/v1/evidence/{id}/validate"""

    @pytest.mark.asyncio
    async def test_validate_evidence(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should update validation status."""
        ev = _make_evidence(validation_status=ValidationStatus.PENDING)
        mock_db_session.execute.return_value = _mock_scalar_result(ev)

        response = await client.patch(
            f"/api/v1/evidence/{ev.id}/validate",
            json={"validation_status": "validated", "actor": "reviewer"},
        )
        assert response.status_code == 200
        assert ev.validation_status == ValidationStatus.VALIDATED
        # Should create audit log
        assert mock_db_session.add.called

    @pytest.mark.asyncio
    async def test_validate_evidence_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 for non-existent evidence."""
        mock_db_session.execute.return_value = _mock_scalar_result(None)

        fake_id = uuid.uuid4()
        response = await client.patch(
            f"/api/v1/evidence/{fake_id}/validate",
            json={"validation_status": "validated"},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Batch Validate
# ---------------------------------------------------------------------------


class TestBatchValidate:
    """POST /api/v1/evidence/validate-batch"""

    @pytest.mark.asyncio
    async def test_batch_validate(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should validate multiple evidence items."""
        ev1 = _make_evidence()
        ev2 = _make_evidence()

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(ev1),
            _mock_scalar_result(ev2),
        ]

        response = await client.post(
            "/api/v1/evidence/validate-batch",
            json={
                "evidence_ids": [str(ev1.id), str(ev2.id)],
                "validation_status": "active",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated_count"] == 2
        assert len(data["errors"]) == 0

    @pytest.mark.asyncio
    async def test_batch_validate_partial_failure(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should report errors for missing items."""
        ev1 = _make_evidence()

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(ev1),
            _mock_scalar_result(None),  # Not found
        ]

        fake_id = uuid.uuid4()
        response = await client.post(
            "/api/v1/evidence/validate-batch",
            json={
                "evidence_ids": [str(ev1.id), str(fake_id)],
                "validation_status": "active",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated_count"] == 1
        assert len(data["errors"]) == 1


# ---------------------------------------------------------------------------
# Get Fragments
# ---------------------------------------------------------------------------


class TestGetFragments:
    """GET /api/v1/evidence/{id}/fragments"""

    @pytest.mark.asyncio
    async def test_get_fragments(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return fragments for an evidence item."""
        ev_id = uuid.uuid4()
        frag1 = _make_fragment(evidence_id=ev_id, fragment_type=FragmentType.TEXT)
        frag2 = _make_fragment(evidence_id=ev_id, fragment_type=FragmentType.TABLE)

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(ev_id),  # verify evidence exists
            _mock_scalars_result([frag1, frag2]),
        ]

        response = await client.get(f"/api/v1/evidence/{ev_id}/fragments")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_get_fragments_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 for non-existent evidence."""
        mock_db_session.execute.return_value = _mock_scalar_result(None)

        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/evidence/{fake_id}/fragments")
        assert response.status_code == 404
