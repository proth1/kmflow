"""Route-level tests for Seed List endpoints (Story #321)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import User, UserRole
from src.core.models.seed_term import SeedTerm, TermCategory, TermSource, TermStatus
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
TERM_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


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


class TestCreateSeedList:
    def test_returns_201_on_bulk_create(self) -> None:
        mock_session = AsyncMock()

        existing_result = MagicMock()
        existing_scalars = MagicMock()
        existing_scalars.all.return_value = []
        existing_result.scalars.return_value = existing_scalars
        mock_session.execute = AsyncMock(return_value=existing_result)

        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/seed-lists",
            json={
                "terms": [
                    {"term": "KYC Review", "domain": "compliance", "category": "activity"},
                    {"term": "Loan Approval", "domain": "lending"},
                ]
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created_count"] == 2

    def test_returns_422_for_empty_terms(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/seed-lists",
            json={"terms": []},
        )
        assert resp.status_code == 422


class TestGetSeedList:
    def test_returns_200_with_items(self) -> None:
        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        term = MagicMock(spec=SeedTerm)
        term.id = TERM_ID
        term.engagement_id = ENGAGEMENT_ID
        term.term = "KYC Review"
        term.domain = "compliance"
        term.category = TermCategory.ACTIVITY
        term.source = TermSource.CONSULTANT_PROVIDED
        term.status = TermStatus.ACTIVE
        term.created_at = datetime(2026, 2, 27, tzinfo=UTC)

        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = [term]
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        client = _make_app(mock_session)
        resp = client.get(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/seed-lists"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["items"][0]["term"] == "KYC Review"


class TestRefineSeedList:
    def test_returns_200_on_discovered_terms(self) -> None:
        mock_session = AsyncMock()

        existing_result = MagicMock()
        existing_scalars = MagicMock()
        existing_scalars.all.return_value = []
        existing_result.scalars.return_value = existing_scalars
        mock_session.execute = AsyncMock(return_value=existing_result)

        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/seed-lists/refine",
            json={
                "terms": [
                    {"term": "Risk Assessment", "domain": "compliance"},
                ]
            },
        )
        assert resp.status_code == 200
        assert resp.json()["created_count"] == 1


class TestGenerateProbes:
    def test_returns_200_with_probes(self) -> None:
        mock_session = AsyncMock()

        term = MagicMock(spec=SeedTerm)
        term.id = TERM_ID
        term.term = "KYC Review"
        term.engagement_id = ENGAGEMENT_ID

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [term]
        result_mock.scalars.return_value = scalars_mock
        mock_session.execute = AsyncMock(return_value=result_mock)

        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/seed-lists/generate-probes"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["probes_generated"] == 4


class TestExtractionTargets:
    def test_returns_200_with_targets(self) -> None:
        mock_session = AsyncMock()

        term = MagicMock(spec=SeedTerm)
        term.id = TERM_ID
        term.term = "KYC Review"
        term.domain = "compliance"
        term.category = TermCategory.ACTIVITY

        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [term]
        result_mock.scalars.return_value = scalars_mock
        mock_session.execute = AsyncMock(return_value=result_mock)

        client = _make_app(mock_session)
        resp = client.get(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/seed-lists/extraction-targets"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_term_count"] == 1


class TestDeprecateSeedTerm:
    def test_returns_200_on_deprecation(self) -> None:
        mock_session = AsyncMock()

        term = MagicMock(spec=SeedTerm)
        term.id = TERM_ID
        term.term = "Old Term"
        term.status = TermStatus.ACTIVE

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = term
        mock_session.execute = AsyncMock(return_value=result_mock)

        client = _make_app(mock_session)
        resp = client.delete(f"/api/v1/seed-terms/{TERM_ID}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deprecated"

    def test_returns_404_for_missing_term(self) -> None:
        mock_session = AsyncMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        client = _make_app(mock_session)
        resp = client.delete(f"/api/v1/seed-terms/{uuid.uuid4()}")
        assert resp.status_code == 404
