"""Tests for the evidence upload endpoint (POST /api/v1/evidence/upload).

Covers:
- Successful multipart upload
- Missing file field (422)
- Missing engagement_id field (422)
- Upload without auth token (401)
- Disallowed file type (415)
- Empty file body (400)
- Invalid metadata JSON (400)
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from src.core.models import EvidenceCategory, EvidenceItem, ValidationStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_evidence_item(**overrides) -> EvidenceItem:  # noqa: ANN003
    """Build a minimal EvidenceItem for use in mock return values.

    Note: quality_score is a computed @property on EvidenceItem with no setter,
    so it must NOT be passed to the constructor.  created_at / updated_at are
    server-default columns that SQLAlchemy does not require at object creation.
    """
    defaults = {
        "id": uuid.uuid4(),
        "engagement_id": uuid.uuid4(),
        "name": "report.pdf",
        "category": EvidenceCategory.DOCUMENTS,
        "format": "pdf",
        "content_hash": "a" * 64,
        "file_path": "/evidence_store/report.pdf",
        "size_bytes": 2048,
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEvidenceUpload:
    """Tests for POST /api/v1/evidence/upload."""

    @pytest.mark.asyncio
    async def test_upload_success(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """A well-formed multipart upload returns 201 with evidence metadata."""
        engagement_id = uuid.uuid4()
        ev = _make_evidence_item(engagement_id=engagement_id)

        # ingest_evidence returns (evidence_item, fragments, duplicate_of_id)
        mock_fragments = [MagicMock(), MagicMock()]
        quality_scores = {
            "completeness": 0.5,
            "reliability": 0.6,
            "freshness": 0.7,
            "consistency": 0.8,
        }

        with (
            patch(
                "src.api.routes.evidence.ingest_evidence",
                new=AsyncMock(return_value=(ev, mock_fragments, None)),
            ),
            patch(
                "src.api.routes.evidence.score_evidence",
                new=AsyncMock(return_value=quality_scores),
            ),
        ):
            response = await client.post(
                "/api/v1/evidence/upload",
                files={"file": ("report.pdf", io.BytesIO(b"PDF content here"), "application/pdf")},
                data={"engagement_id": str(engagement_id)},
            )

        assert response.status_code == 201
        data = response.json()
        assert "evidence" in data
        assert data["fragment_count"] == 2
        assert data["duplicate_of_id"] is None
        assert "quality_scores" in data
        assert data["evidence"]["name"] == "report.pdf"

    @pytest.mark.asyncio
    async def test_upload_missing_file_returns_422(self, client: AsyncClient) -> None:
        """Omitting the file field in a multipart form returns 422."""
        engagement_id = uuid.uuid4()
        response = await client.post(
            "/api/v1/evidence/upload",
            data={"engagement_id": str(engagement_id)},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_upload_missing_engagement_id_returns_422(self, client: AsyncClient) -> None:
        """Omitting engagement_id in a multipart form returns 422."""
        response = await client.post(
            "/api/v1/evidence/upload",
            files={"file": ("report.pdf", io.BytesIO(b"PDF content"), "application/pdf")},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_upload_unauthorized_returns_401(
        self, test_app, mock_db_session: AsyncMock
    ) -> None:
        """Uploading without any Authorization header returns 401.

        We temporarily remove the get_current_user override to exercise the
        real auth dependency path.
        """
        from src.core.auth import get_current_user

        test_app.dependency_overrides.pop(get_current_user, None)
        try:
            from httpx import ASGITransport, AsyncClient as RawClient

            transport = ASGITransport(app=test_app)
            async with RawClient(transport=transport, base_url="http://test") as bare_client:
                response = await bare_client.post(
                    "/api/v1/evidence/upload",
                    files={
                        "file": ("report.pdf", io.BytesIO(b"PDF content"), "application/pdf")
                    },
                    data={"engagement_id": str(uuid.uuid4())},
                )
        finally:
            # Restore the override so other tests in the session are unaffected
            from unittest.mock import MagicMock
            from src.core.models import User, UserRole

            mock_user = MagicMock(spec=User)
            mock_user.id = uuid.uuid4()
            mock_user.email = "testuser@kmflow.dev"
            mock_user.role = UserRole.PLATFORM_ADMIN
            mock_user.is_active = True
            test_app.dependency_overrides[get_current_user] = lambda: mock_user

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_invalid_file_type_returns_415(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Uploading a disallowed file type returns 415 Unsupported Media Type.

        The validation happens inside ingest_evidence (via validate_file_type).
        We simulate this by making ingest_evidence raise the HTTPException
        that validate_file_type would raise.
        """
        from fastapi import HTTPException

        with patch(
            "src.api.routes.evidence.ingest_evidence",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=415,
                    detail="File type 'application/x-executable' is not allowed.",
                )
            ),
        ):
            response = await client.post(
                "/api/v1/evidence/upload",
                files={
                    "file": (
                        "malware.exe",
                        io.BytesIO(b"\x4d\x5a\x90\x00"),
                        "application/x-executable",
                    )
                },
                data={"engagement_id": str(uuid.uuid4())},
            )

        assert response.status_code == 415

    @pytest.mark.asyncio
    async def test_upload_empty_file_returns_400(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Uploading a zero-byte file returns 400 Bad Request."""
        response = await client.post(
            "/api/v1/evidence/upload",
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
            data={"engagement_id": str(uuid.uuid4())},
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_invalid_metadata_json_returns_400(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Passing malformed JSON in the metadata field returns 400."""
        response = await client.post(
            "/api/v1/evidence/upload",
            files={"file": ("report.pdf", io.BytesIO(b"PDF content here"), "application/pdf")},
            data={
                "engagement_id": str(uuid.uuid4()),
                "metadata": "{not valid json",
            },
        )
        assert response.status_code == 400
        assert "json" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_reports_duplicate(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """When a duplicate is detected, the response includes duplicate_of_id."""
        engagement_id = uuid.uuid4()
        original_id = uuid.uuid4()
        ev = _make_evidence_item(engagement_id=engagement_id, duplicate_of_id=original_id)

        with (
            patch(
                "src.api.routes.evidence.ingest_evidence",
                new=AsyncMock(return_value=(ev, [], original_id)),
            ),
            patch(
                "src.api.routes.evidence.score_evidence",
                new=AsyncMock(return_value={}),
            ),
        ):
            response = await client.post(
                "/api/v1/evidence/upload",
                files={"file": ("dup.pdf", io.BytesIO(b"duplicate content"), "application/pdf")},
                data={"engagement_id": str(engagement_id)},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["duplicate_of_id"] == str(original_id)
        assert data["fragment_count"] == 0
