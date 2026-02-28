"""Route-level tests for Financial Assumption Management (Story #354).

Tests the engagement-scoped assumption endpoints.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import FinancialAssumption, FinancialAssumptionType, FinancialAssumptionVersion, User, UserRole
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
EVIDENCE_ID = uuid.uuid4()
ASSUMPTION_ID = uuid.uuid4()


def _mock_user() -> User:
    user = MagicMock(spec=User)
    user.id = USER_ID
    user.email = "lead@example.com"
    user.role = UserRole.ENGAGEMENT_LEAD
    return user


def _make_client(mock_session: AsyncMock) -> TestClient:
    app = create_app()
    app.state.neo4j_driver = MagicMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.dependency_overrides[require_engagement_access] = lambda: _mock_user()
    return TestClient(app)


class TestCreateAssumption:
    """POST /api/v1/engagements/{id}/assumptions"""

    @patch("src.api.routes.assumptions.create_assumption")
    def test_create_with_evidence_returns_201(self, mock_create) -> None:
        assumption = MagicMock(spec=FinancialAssumption)
        assumption.id = ASSUMPTION_ID
        assumption.engagement_id = ENGAGEMENT_ID
        assumption.assumption_type = FinancialAssumptionType.COST_PER_ROLE
        assumption.name = "Rate"
        assumption.value = 150.0
        assumption.unit = "USD/hour"
        assumption.confidence = 0.8
        assumption.confidence_range = 0.20
        assumption.source_evidence_id = EVIDENCE_ID
        assumption.confidence_explanation = None
        assumption.notes = None
        assumption.created_at = None
        assumption.updated_at = None
        mock_create.return_value = assumption

        session = AsyncMock()
        client = _make_client(session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/assumptions",
            json={
                "assumption_type": "cost_per_role",
                "name": "Rate",
                "value": 150.0,
                "unit": "USD/hour",
                "confidence": 0.8,
                "source_evidence_id": str(EVIDENCE_ID),
                "confidence_range": 0.20,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["value"] == 150.0
        assert data["confidence_range"] == 0.20

    def test_create_without_source_or_explanation_returns_422(self) -> None:
        session = AsyncMock()
        client = _make_client(session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/assumptions",
            json={
                "assumption_type": "cost_per_role",
                "name": "Rate",
                "value": 100.0,
                "unit": "USD/hour",
                "confidence": 0.5,
            },
        )
        assert resp.status_code == 422


class TestListAssumptions:
    """GET /api/v1/engagements/{id}/assumptions"""

    @patch("src.api.routes.assumptions.list_assumptions")
    def test_list_returns_items(self, mock_list) -> None:
        assumption = MagicMock(spec=FinancialAssumption)
        assumption.id = ASSUMPTION_ID
        assumption.engagement_id = ENGAGEMENT_ID
        assumption.assumption_type = FinancialAssumptionType.COST_PER_ROLE
        assumption.name = "Rate"
        assumption.value = 150.0
        assumption.unit = "USD/hour"
        assumption.confidence = 0.8
        assumption.confidence_range = None
        assumption.source_evidence_id = EVIDENCE_ID
        assumption.confidence_explanation = None
        assumption.notes = None
        assumption.created_at = None
        assumption.updated_at = None
        mock_list.return_value = {"items": [assumption], "total": 1}

        session = AsyncMock()
        client = _make_client(session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/assumptions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    @patch("src.api.routes.assumptions.list_assumptions")
    def test_list_filters_by_type(self, mock_list) -> None:
        mock_list.return_value = {"items": [], "total": 0}
        session = AsyncMock()
        client = _make_client(session)
        resp = client.get(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/assumptions?assumption_type=technology_cost"
        )
        assert resp.status_code == 200
        mock_list.assert_called_once()
        call_args = mock_list.call_args
        assert call_args[0][2] == FinancialAssumptionType.TECHNOLOGY_COST


class TestUpdateAssumption:
    """PATCH /api/v1/engagements/{id}/assumptions/{assumption_id}"""

    @patch("src.api.routes.assumptions.update_assumption")
    def test_update_returns_updated(self, mock_update) -> None:
        assumption = MagicMock(spec=FinancialAssumption)
        assumption.id = ASSUMPTION_ID
        assumption.engagement_id = ENGAGEMENT_ID
        assumption.assumption_type = FinancialAssumptionType.COST_PER_ROLE
        assumption.name = "Rate"
        assumption.value = 165.0
        assumption.unit = "USD/hour"
        assumption.confidence = 0.8
        assumption.confidence_range = None
        assumption.source_evidence_id = EVIDENCE_ID
        assumption.confidence_explanation = None
        assumption.notes = None
        assumption.created_at = None
        assumption.updated_at = None
        mock_update.return_value = assumption

        session = AsyncMock()
        client = _make_client(session)
        resp = client.patch(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/assumptions/{ASSUMPTION_ID}",
            json={"value": 165.0},
        )
        assert resp.status_code == 200
        assert resp.json()["value"] == 165.0

    @patch("src.api.routes.assumptions.update_assumption")
    def test_update_not_found_returns_404(self, mock_update) -> None:
        mock_update.side_effect = ValueError("Assumption not found")
        session = AsyncMock()
        client = _make_client(session)
        resp = client.patch(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/assumptions/{uuid.uuid4()}",
            json={"value": 100.0},
        )
        assert resp.status_code == 404


class TestAssumptionHistory:
    """GET /api/v1/engagements/{id}/assumptions/{assumption_id}/history"""

    @patch("src.api.routes.assumptions.get_assumption_history")
    def test_history_returns_versions(self, mock_history) -> None:
        version = MagicMock(spec=FinancialAssumptionVersion)
        version.id = uuid.uuid4()
        version.value = 150.0
        version.unit = "USD/hour"
        version.confidence = 0.8
        version.confidence_range = None
        version.source_evidence_id = None
        version.confidence_explanation = None
        version.notes = None
        version.changed_by = USER_ID
        version.changed_at = None
        mock_history.return_value = [version]

        session = AsyncMock()
        client = _make_client(session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/assumptions/{ASSUMPTION_ID}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["assumption_id"] == str(ASSUMPTION_ID)
        assert len(data["versions"]) == 1
        assert data["versions"][0]["value"] == 150.0
