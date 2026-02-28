"""Route-level tests for Validation APIs (Story #365).

Tests pack detail retrieval, filtered decision listing, and reviewer routing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import User, UserRole
from src.core.models.role_activity_mapping import RoleActivityMapping
from src.core.models.validation import ReviewPack, ReviewPackStatus
from src.core.models.validation_decision import ValidationDecision
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
REVIEW_PACK_ID = uuid.uuid4()
POV_VERSION_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
REVIEWER_ID = uuid.uuid4()


def _mock_user(role: UserRole = UserRole.ENGAGEMENT_LEAD) -> User:
    user = MagicMock(spec=User)
    user.id = USER_ID
    user.email = "lead@example.com"
    user.role = role
    return user


def _make_app(mock_session: AsyncMock) -> TestClient:
    app = create_app()
    app.state.neo4j_driver = MagicMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.dependency_overrides[require_engagement_access] = lambda: _mock_user()
    return TestClient(app)


def _mock_review_pack(
    pack_id: uuid.UUID | None = None,
    engagement_id: uuid.UUID | None = None,
) -> MagicMock:
    pack = MagicMock(spec=ReviewPack)
    pack.id = pack_id or REVIEW_PACK_ID
    pack.engagement_id = engagement_id or ENGAGEMENT_ID
    pack.pov_version_id = POV_VERSION_ID
    pack.segment_index = 0
    pack.segment_activities = [{"id": "act_1", "name": "Activity 1"}]
    pack.activity_count = 1
    pack.evidence_list = ["ev_1"]
    pack.confidence_scores = {"act_1": 0.75}
    pack.conflict_flags = []
    pack.seed_terms = ["term_1"]
    pack.assigned_sme_id = None
    pack.assigned_role = None
    pack.status = ReviewPackStatus.PENDING.value
    pack.avg_confidence = 0.75
    pack.created_at = datetime(2026, 2, 27, tzinfo=UTC)
    return pack


def _mock_decision(
    decision_id: uuid.UUID | None = None,
    action: str = "confirm",
    reviewer_id: uuid.UUID | None = None,
) -> MagicMock:
    dec = MagicMock(spec=ValidationDecision)
    dec.id = decision_id or uuid.uuid4()
    dec.engagement_id = ENGAGEMENT_ID
    dec.review_pack_id = REVIEW_PACK_ID
    dec.element_id = "elem_001"
    dec.action = action
    dec.reviewer_id = reviewer_id or REVIEWER_ID
    dec.payload = None
    dec.graph_write_back_result = {"action": action}
    dec.decision_at = datetime(2026, 2, 27, 10, 0, 0, tzinfo=UTC)
    return dec


# ── Scenario 1: Review Pack Detail Retrieval ──────────────────────────


class TestGetReviewPack:
    """GET /api/v1/validation/review-packs/{id}"""

    def test_returns_200_for_existing_pack(self) -> None:
        pack = _mock_review_pack()
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=pack)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        client = _make_app(mock_session)
        resp = client.get(
            f"/api/v1/validation/review-packs/{REVIEW_PACK_ID}"
            f"?engagement_id={ENGAGEMENT_ID}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["segment_activities"] == [{"id": "act_1", "name": "Activity 1"}]
        assert data["evidence_list"] == ["ev_1"]
        assert data["confidence_scores"] == {"act_1": 0.75}

    def test_returns_404_for_missing_pack(self) -> None:
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        client = _make_app(mock_session)
        resp = client.get(
            f"/api/v1/validation/review-packs/{uuid.uuid4()}"
            f"?engagement_id={ENGAGEMENT_ID}"
        )
        assert resp.status_code == 404

    def test_returns_404_for_wrong_engagement(self) -> None:
        """IDOR test: pack exists but belongs to different engagement."""
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        wrong_engagement = uuid.uuid4()
        client = _make_app(mock_session)
        resp = client.get(
            f"/api/v1/validation/review-packs/{REVIEW_PACK_ID}"
            f"?engagement_id={wrong_engagement}"
        )
        assert resp.status_code == 404


# ── Scenario 2: Filtered Decision Listing ─────────────────────────────


class TestListDecisions:
    """GET /api/v1/validation/decisions"""

    def _setup_session(
        self, decisions: list[MagicMock], total: int = 0,
    ) -> AsyncMock:
        """Create mock session that handles both count and list queries."""
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = AsyncMock()
            if call_count == 1:
                # Count query
                result.scalar = MagicMock(return_value=total or len(decisions))
            else:
                # List query
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=decisions)
                result.scalars = MagicMock(return_value=mock_scalars)
            return result

        session = AsyncMock()
        session.execute = mock_execute
        return session

    def test_returns_200_with_decisions(self) -> None:
        decisions = [_mock_decision(), _mock_decision(action="reject")]
        session = self._setup_session(decisions, total=2)

        client = _make_app(session)
        resp = client.get(
            f"/api/v1/validation/decisions?engagement_id={ENGAGEMENT_ID}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert "limit" in data
        assert "offset" in data

    def test_returns_empty_list(self) -> None:
        session = self._setup_session([], total=0)

        client = _make_app(session)
        resp = client.get(
            f"/api/v1/validation/decisions?engagement_id={ENGAGEMENT_ID}"
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["total"] == 0

    def test_filter_by_action(self) -> None:
        decisions = [_mock_decision(action="confirm")]
        session = self._setup_session(decisions, total=1)

        client = _make_app(session)
        resp = client.get(
            f"/api/v1/validation/decisions?engagement_id={ENGAGEMENT_ID}&action=confirm"
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_filter_by_reviewer(self) -> None:
        decisions = [_mock_decision(reviewer_id=REVIEWER_ID)]
        session = self._setup_session(decisions, total=1)

        client = _make_app(session)
        resp = client.get(
            f"/api/v1/validation/decisions?engagement_id={ENGAGEMENT_ID}&reviewer_id={REVIEWER_ID}"
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_filter_by_review_pack(self) -> None:
        decisions = [_mock_decision()]
        session = self._setup_session(decisions, total=1)

        client = _make_app(session)
        resp = client.get(
            f"/api/v1/validation/decisions?engagement_id={ENGAGEMENT_ID}"
            f"&review_pack_id={REVIEW_PACK_ID}"
        )
        assert resp.status_code == 200

    def test_pagination_params(self) -> None:
        decisions = [_mock_decision()]
        session = self._setup_session(decisions, total=50)

        client = _make_app(session)
        resp = client.get(
            f"/api/v1/validation/decisions?engagement_id={ENGAGEMENT_ID}"
            "&limit=10&offset=20"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 20

    def test_requires_engagement_id(self) -> None:
        session = AsyncMock()
        client = _make_app(session)
        resp = client.get("/api/v1/validation/decisions")
        assert resp.status_code == 422


# ── Scenario 3: Role-Based Reviewer Routing ──────────────────────────


def _mock_role_mapping(
    role_name: str,
    reviewer_id: uuid.UUID,
    engagement_id: uuid.UUID | None = None,
) -> MagicMock:
    mapping = MagicMock(spec=RoleActivityMapping)
    mapping.engagement_id = engagement_id or ENGAGEMENT_ID
    mapping.role_name = role_name
    mapping.reviewer_id = reviewer_id
    return mapping


class TestReviewerRouting:
    """POST /api/v1/validation/review-packs/route"""

    def _setup_routing_session(
        self,
        mappings: list[MagicMock],
        packs: list[MagicMock],
    ) -> AsyncMock:
        """Create mock session for routing queries (mappings + packs)."""
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = AsyncMock()
            mock_scalars = MagicMock()
            if call_count == 1:
                # Mappings query
                mock_scalars.all = MagicMock(return_value=mappings)
            else:
                # Packs query
                mock_scalars.all = MagicMock(return_value=packs)
            result.scalars = MagicMock(return_value=mock_scalars)
            return result

        session = AsyncMock()
        session.execute = mock_execute
        session.commit = AsyncMock()
        return session

    def test_routes_packs_to_matching_reviewer(self) -> None:
        """Packs with matching role-activity mapping get assigned_sme_id set."""
        ops_reviewer = uuid.uuid4()
        mappings = [_mock_role_mapping("Operations Manager", ops_reviewer)]

        pack = _mock_review_pack()
        pack.assigned_role = "Operations Manager"
        pack.assigned_sme_id = None

        session = self._setup_routing_session(mappings, [pack])
        client = _make_app(session)
        resp = client.post(
            "/api/v1/validation/review-packs/route",
            json={"engagement_id": str(ENGAGEMENT_ID)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["assigned_role"] == "Operations Manager"
        assert data[0]["assigned_sme_id"] == str(ops_reviewer)
        assert data[0]["status"] == "routed"

    def test_unmatched_role_remains_unassigned(self) -> None:
        """Packs with no matching mapping stay unassigned."""
        mappings = [_mock_role_mapping("Finance Analyst", uuid.uuid4())]

        pack = _mock_review_pack()
        pack.assigned_role = "Operations Manager"
        pack.assigned_sme_id = None

        session = self._setup_routing_session(mappings, [pack])
        client = _make_app(session)
        resp = client.post(
            "/api/v1/validation/review-packs/route",
            json={"engagement_id": str(ENGAGEMENT_ID)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "unassigned"
        assert data[0]["assigned_sme_id"] is None

    def test_no_role_on_pack_stays_unassigned(self) -> None:
        """Packs with no assigned_role remain unassigned."""
        mappings = [_mock_role_mapping("Operations Manager", uuid.uuid4())]

        pack = _mock_review_pack()
        pack.assigned_role = None
        pack.assigned_sme_id = None

        session = self._setup_routing_session(mappings, [pack])
        client = _make_app(session)
        resp = client.post(
            "/api/v1/validation/review-packs/route",
            json={"engagement_id": str(ENGAGEMENT_ID)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["status"] == "unassigned"

    def test_empty_packs_returns_empty_list(self) -> None:
        """No unassigned packs returns empty list."""
        session = self._setup_routing_session([], [])
        client = _make_app(session)
        resp = client.post(
            "/api/v1/validation/review-packs/route",
            json={"engagement_id": str(ENGAGEMENT_ID)},
        )
        assert resp.status_code == 200
        assert resp.json() == []
