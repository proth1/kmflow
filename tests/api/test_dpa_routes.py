"""Route-level tests for DPA tracking endpoints (GDPR Article 28)."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import User, UserRole
from src.core.models.gdpr import DpaStatus, LawfulBasis
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
DPA_ID = uuid.uuid4()


def _mock_user(role: UserRole = UserRole.ENGAGEMENT_LEAD) -> User:
    user = MagicMock(spec=User)
    user.id = USER_ID
    user.email = "lead@example.com"
    user.role = role
    return user


def _make_app(
    mock_session: AsyncMock,
    role: UserRole = UserRole.ENGAGEMENT_LEAD,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user(role)
    app.dependency_overrides[require_engagement_access] = lambda: _mock_user(role)
    return TestClient(app)


def _mock_dpa(
    status: DpaStatus = DpaStatus.DRAFT,
    dpa_id: uuid.UUID | None = None,
) -> MagicMock:
    from src.core.models.gdpr import DataProcessingAgreement

    dpa = MagicMock(spec=DataProcessingAgreement)
    dpa.id = dpa_id or DPA_ID
    dpa.engagement_id = ENGAGEMENT_ID
    dpa.reference_number = "DPA-2026-001"
    dpa.version = "1.0"
    dpa.status = status
    dpa.effective_date = date(2026, 1, 1)
    dpa.expiry_date = date(2027, 1, 1)
    dpa.controller_name = "Client Corp"
    dpa.processor_name = "Consulting Firm LLP"
    dpa.data_categories = ["personal_data", "financial_data"]
    dpa.sub_processors = None
    dpa.retention_days_override = None
    dpa.lawful_basis = LawfulBasis.CONTRACT
    dpa.notes = None
    dpa.created_by = USER_ID
    dpa.created_at = None
    dpa.updated_at = None
    return dpa


DPA_PAYLOAD = {
    "reference_number": "DPA-2026-001",
    "version": "1.0",
    "effective_date": "2026-01-01",
    "controller_name": "Client Corp",
    "processor_name": "Consulting Firm LLP",
    "data_categories": ["personal_data", "financial_data"],
    "lawful_basis": "contract",
}


class TestCreateDpa:
    def test_create_returns_201(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_dpa = _mock_dpa()

        with patch("src.api.routes.dpa.GdprComplianceService") as mock_svc_cls:
            mock_svc_cls.return_value.create_dpa = AsyncMock(return_value=mock_dpa)
            client = _make_app(mock_session)
            resp = client.post(
                f"/api/v1/engagements/{ENGAGEMENT_ID}/dpa/",
                json=DPA_PAYLOAD,
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["reference_number"] == "DPA-2026-001"
        assert data["status"] == "draft"

    def test_create_calls_audit_log(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_dpa = _mock_dpa()

        with (
            patch("src.api.routes.dpa.GdprComplianceService") as mock_svc_cls,
            patch("src.api.routes.dpa.log_audit") as mock_audit,
        ):
            mock_svc_cls.return_value.create_dpa = AsyncMock(return_value=mock_dpa)
            client = _make_app(mock_session)
            resp = client.post(
                f"/api/v1/engagements/{ENGAGEMENT_ID}/dpa/",
                json=DPA_PAYLOAD,
            )

        assert resp.status_code == 201
        mock_audit.assert_called_once()


class TestActivateDpa:
    def test_activate_returns_200(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        active_dpa = _mock_dpa(status=DpaStatus.ACTIVE)

        with patch("src.api.routes.dpa.GdprComplianceService") as mock_svc_cls:
            mock_svc_cls.return_value.activate_dpa = AsyncMock(return_value=active_dpa)
            client = _make_app(mock_session)
            resp = client.post(
                f"/api/v1/engagements/{ENGAGEMENT_ID}/dpa/{DPA_ID}/activate",
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_activate_supersedes_previous(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        active_dpa = _mock_dpa(status=DpaStatus.ACTIVE)

        with patch("src.api.routes.dpa.GdprComplianceService") as mock_svc_cls:
            service = mock_svc_cls.return_value
            service.activate_dpa = AsyncMock(return_value=active_dpa)
            client = _make_app(mock_session)
            resp = client.post(
                f"/api/v1/engagements/{ENGAGEMENT_ID}/dpa/{DPA_ID}/activate",
            )

        assert resp.status_code == 200
        service.activate_dpa.assert_called_once_with(ENGAGEMENT_ID, DPA_ID)

    def test_activate_invalid_status_returns_400(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        with patch("src.api.routes.dpa.GdprComplianceService") as mock_svc_cls:
            mock_svc_cls.return_value.activate_dpa = AsyncMock(
                side_effect=ValueError("Cannot activate DPA in status expired")
            )
            client = _make_app(mock_session)
            resp = client.post(
                f"/api/v1/engagements/{ENGAGEMENT_ID}/dpa/{DPA_ID}/activate",
            )

        assert resp.status_code == 400


class TestGetActiveDpa:
    def test_returns_active_dpa(self) -> None:
        mock_session = AsyncMock()
        active_dpa = _mock_dpa(status=DpaStatus.ACTIVE)

        with patch("src.api.routes.dpa.GdprComplianceService") as mock_svc_cls:
            mock_svc_cls.return_value.get_active_dpa = AsyncMock(return_value=active_dpa)
            client = _make_app(mock_session)
            resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/dpa/")

        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_returns_404_when_missing(self) -> None:
        mock_session = AsyncMock()

        with patch("src.api.routes.dpa.GdprComplianceService") as mock_svc_cls:
            mock_svc_cls.return_value.get_active_dpa = AsyncMock(return_value=None)
            client = _make_app(mock_session)
            resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/dpa/")

        assert resp.status_code == 404


class TestListDpaHistory:
    def test_list_returns_all_versions(self) -> None:
        mock_session = AsyncMock()
        dpas = [_mock_dpa(DpaStatus.SUPERSEDED), _mock_dpa(DpaStatus.ACTIVE, dpa_id=uuid.uuid4())]

        with patch("src.api.routes.dpa.GdprComplianceService") as mock_svc_cls:
            mock_svc_cls.return_value.list_dpas = AsyncMock(return_value={"items": dpas, "total": 2})
            client = _make_app(mock_session)
            resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/dpa/history")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2


class TestUpdateDpa:
    def test_update_returns_updated_dpa(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        updated = _mock_dpa()
        updated.notes = "Updated notes"

        with patch("src.api.routes.dpa.GdprComplianceService") as mock_svc_cls:
            mock_svc_cls.return_value.update_dpa = AsyncMock(return_value=updated)
            client = _make_app(mock_session)
            resp = client.patch(
                f"/api/v1/engagements/{ENGAGEMENT_ID}/dpa/{DPA_ID}",
                json={"notes": "Updated notes"},
            )

        assert resp.status_code == 200


class TestEngagementDpaCompliance:
    def test_engagement_get_includes_dpa_compliance(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        # Mock the engagement query
        from src.core.models.engagement import Engagement

        engagement = MagicMock(spec=Engagement)
        engagement.id = ENGAGEMENT_ID
        engagement.name = "Test Engagement"
        engagement.client = "Test Client"
        engagement.business_area = "Banking"
        engagement.description = None
        engagement.status = "draft"
        engagement.team = []
        engagement.data_residency_restriction = "none"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = engagement
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("src.api.routes.engagements.GdprComplianceService") as mock_svc_cls:
            mock_svc_cls.return_value.get_dpa_compliance_summary = AsyncMock(
                return_value={
                    "status": "missing",
                    "reference_number": None,
                    "effective_date": None,
                    "expiry_date": None,
                    "dpa_id": None,
                }
            )
            client = _make_app(mock_session)
            resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert "dpa_compliance" in data
        assert data["dpa_compliance"]["status"] == "missing"


class TestEvidenceUploadDpaWarning:
    def test_upload_warns_without_active_dpa(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        # Mock evidence item
        from src.core.models.evidence import EvidenceItem

        evidence = MagicMock(spec=EvidenceItem)
        evidence.id = uuid.uuid4()
        evidence.engagement_id = ENGAGEMENT_ID
        evidence.name = "test.pdf"
        evidence.category = "documents"
        evidence.format = "pdf"
        evidence.content_hash = "abc123"
        evidence.file_path = "/tmp/test.pdf"
        evidence.size_bytes = 1024
        evidence.mime_type = "application/pdf"
        evidence.metadata_json = None
        evidence.source_date = None
        evidence.completeness_score = 1.0
        evidence.reliability_score = 1.0
        evidence.freshness_score = 1.0
        evidence.consistency_score = 1.0
        evidence.quality_score = 1.0
        evidence.duplicate_of_id = None
        evidence.validation_status = "pending"
        evidence.classification = "internal"
        evidence.created_at = None
        evidence.updated_at = None

        with (
            patch("src.api.routes.evidence.ingest_evidence", new_callable=AsyncMock) as mock_ingest,
            patch("src.api.routes.evidence.score_evidence", new_callable=AsyncMock) as mock_score,
            patch("src.api.routes.evidence.GdprComplianceService") as mock_gdpr_cls,
        ):
            mock_ingest.return_value = (evidence, [], None)
            mock_score.return_value = {"quality": 1.0}
            mock_gdpr_cls.return_value.get_active_dpa = AsyncMock(return_value=None)

            client = _make_app(mock_session)
            resp = client.post(
                "/api/v1/evidence/upload",
                data={"engagement_id": str(ENGAGEMENT_ID)},
                files={"file": ("test.pdf", b"test content", "application/pdf")},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert len(data["warnings"]) == 1
        assert "dpa_warning" in data["warnings"][0]

    def test_upload_no_warning_with_active_dpa(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        from src.core.models.evidence import EvidenceItem

        evidence = MagicMock(spec=EvidenceItem)
        evidence.id = uuid.uuid4()
        evidence.engagement_id = ENGAGEMENT_ID
        evidence.name = "test.pdf"
        evidence.category = "documents"
        evidence.format = "pdf"
        evidence.content_hash = "abc123"
        evidence.file_path = "/tmp/test.pdf"
        evidence.size_bytes = 1024
        evidence.mime_type = "application/pdf"
        evidence.metadata_json = None
        evidence.source_date = None
        evidence.completeness_score = 1.0
        evidence.reliability_score = 1.0
        evidence.freshness_score = 1.0
        evidence.consistency_score = 1.0
        evidence.quality_score = 1.0
        evidence.duplicate_of_id = None
        evidence.validation_status = "pending"
        evidence.classification = "internal"
        evidence.created_at = None
        evidence.updated_at = None

        active_dpa = _mock_dpa(status=DpaStatus.ACTIVE)

        with (
            patch("src.api.routes.evidence.ingest_evidence", new_callable=AsyncMock) as mock_ingest,
            patch("src.api.routes.evidence.score_evidence", new_callable=AsyncMock) as mock_score,
            patch("src.api.routes.evidence.GdprComplianceService") as mock_gdpr_cls,
        ):
            mock_ingest.return_value = (evidence, [], None)
            mock_score.return_value = {"quality": 1.0}
            mock_gdpr_cls.return_value.get_active_dpa = AsyncMock(return_value=active_dpa)

            client = _make_app(mock_session)
            resp = client.post(
                "/api/v1/evidence/upload",
                data={"engagement_id": str(ENGAGEMENT_ID)},
                files={"file": ("test.pdf", b"test content", "application/pdf")},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["warnings"] == []


class TestDpaRetentionOverride:
    @pytest.mark.asyncio
    async def test_effective_retention_uses_dpa_override(self) -> None:
        """Test that DPA retention override takes precedence."""
        from src.core.services.gdpr_service import GdprComplianceService

        mock_session = AsyncMock()
        dpa = _mock_dpa(status=DpaStatus.ACTIVE)
        dpa.retention_days_override = 180

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dpa
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = GdprComplianceService(mock_session)
        result = await service.get_effective_retention_days(ENGAGEMENT_ID)
        assert result == 180
