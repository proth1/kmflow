"""Route-level tests for Survey Claims endpoints (Story #322)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import User, UserRole
from src.core.models.survey import CertaintyTier, ProbeType, SurveyClaim
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
CLAIM_ID = uuid.uuid4()
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


class TestListSurveyClaims:
    def test_returns_200_with_claims(self) -> None:
        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        claim = MagicMock(spec=SurveyClaim)
        claim.id = CLAIM_ID
        claim.engagement_id = ENGAGEMENT_ID
        claim.session_id = uuid.uuid4()
        claim.probe_type = ProbeType.EXISTENCE
        claim.respondent_role = "operations_team"
        claim.claim_text = "Test claim"
        claim.certainty_tier = CertaintyTier.SUSPECTED
        claim.proof_expectation = "Audit log"
        claim.created_at = datetime(2026, 2, 27, tzinfo=UTC)

        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = [claim]
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        client = _make_app(mock_session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-claims")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert len(data["items"]) == 1

    def test_returns_200_with_tier_filter(self) -> None:
        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = []
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        client = _make_app(mock_session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-claims?certainty_tier=unknown")
        assert resp.status_code == 200
        assert resp.json()["total_count"] == 0


class TestGetSurveyClaim:
    def test_returns_200_for_existing_claim(self) -> None:
        mock_session = AsyncMock()

        claim = MagicMock(spec=SurveyClaim)
        claim.id = CLAIM_ID
        claim.engagement_id = ENGAGEMENT_ID
        claim.session_id = uuid.uuid4()
        claim.probe_type = ProbeType.EXISTENCE
        claim.respondent_role = "operations_team"
        claim.claim_text = "Test claim"
        claim.certainty_tier = CertaintyTier.SUSPECTED
        claim.proof_expectation = "Audit log"
        claim.created_at = datetime(2026, 2, 27, tzinfo=UTC)

        result = MagicMock()
        result.scalar_one_or_none.return_value = claim
        mock_session.execute = AsyncMock(return_value=result)

        client = _make_app(mock_session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-claims/{CLAIM_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(CLAIM_ID)
        assert data["certainty_tier"] == "suspected"

    def test_returns_404_for_wrong_engagement(self) -> None:
        mock_session = AsyncMock()

        claim = MagicMock(spec=SurveyClaim)
        claim.id = CLAIM_ID
        claim.engagement_id = uuid.uuid4()  # Different engagement

        result = MagicMock()
        result.scalar_one_or_none.return_value = claim
        mock_session.execute = AsyncMock(return_value=result)

        client = _make_app(mock_session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-claims/{CLAIM_ID}")
        assert resp.status_code == 404


class TestUpdateSurveyClaim:
    def test_returns_200_on_tier_change(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        claim = MagicMock(spec=SurveyClaim)
        claim.id = CLAIM_ID
        claim.certainty_tier = CertaintyTier.SUSPECTED

        result = MagicMock()
        result.scalar_one_or_none.return_value = claim
        mock_session.execute = AsyncMock(return_value=result)

        client = _make_app(mock_session)
        resp = client.patch(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-claims/{CLAIM_ID}",
            json={"certainty_tier": "known"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_tier"] == "known"

    def test_returns_404_for_missing_claim(self) -> None:
        mock_session = AsyncMock()

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result)

        client = _make_app(mock_session)
        resp = client.patch(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-claims/{uuid.uuid4()}",
            json={"certainty_tier": "known"},
        )
        assert resp.status_code == 404


class TestCreateShelfDataRequest:
    def test_returns_201_for_suspected_claim(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        claim = MagicMock(spec=SurveyClaim)
        claim.id = CLAIM_ID
        claim.engagement_id = ENGAGEMENT_ID
        claim.certainty_tier = CertaintyTier.SUSPECTED
        claim.proof_expectation = "system audit log"
        claim.claim_text = "KYC step completes"

        result = MagicMock()
        result.scalar_one_or_none.return_value = claim
        mock_session.execute = AsyncMock(return_value=result)

        client = _make_app(mock_session)
        resp = client.post(f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-claims/{CLAIM_ID}/shelf-data-request")
        assert resp.status_code == 201

    def test_returns_422_for_non_suspected_claim(self) -> None:
        mock_session = AsyncMock()

        claim = MagicMock(spec=SurveyClaim)
        claim.id = CLAIM_ID
        claim.certainty_tier = CertaintyTier.KNOWN
        claim.proof_expectation = "audit log"

        result = MagicMock()
        result.scalar_one_or_none.return_value = claim
        mock_session.execute = AsyncMock(return_value=result)

        client = _make_app(mock_session)
        resp = client.post(f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-claims/{CLAIM_ID}/shelf-data-request")
        assert resp.status_code == 422


class TestGetClaimHistory:
    def test_returns_200_with_history(self) -> None:
        mock_session = AsyncMock()

        claim = MagicMock(spec=SurveyClaim)
        claim.id = CLAIM_ID
        claim.engagement_id = ENGAGEMENT_ID

        # First execute: get_claim, second: get_claim_history
        claim_result = MagicMock()
        claim_result.scalar_one_or_none.return_value = claim

        history_result = MagicMock()
        history_scalars = MagicMock()
        history_scalars.all.return_value = []
        history_result.scalars.return_value = history_scalars

        mock_session.execute = AsyncMock(side_effect=[claim_result, history_result])

        client = _make_app(mock_session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-claims/{CLAIM_ID}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["claim_id"] == str(CLAIM_ID)
        assert data["history"] == []

    def test_returns_404_for_wrong_engagement(self) -> None:
        mock_session = AsyncMock()

        claim = MagicMock(spec=SurveyClaim)
        claim.id = CLAIM_ID
        claim.engagement_id = uuid.uuid4()  # Different engagement

        result = MagicMock()
        result.scalar_one_or_none.return_value = claim
        mock_session.execute = AsyncMock(return_value=result)

        client = _make_app(mock_session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-claims/{CLAIM_ID}/history")
        assert resp.status_code == 404
