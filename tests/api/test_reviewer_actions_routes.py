"""Route-level tests for reviewer decision endpoint (Story #353)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import User, UserRole
from src.core.models.validation import ReviewPack, ReviewPackStatus
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
REVIEW_PACK_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


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
    pack.status = ReviewPackStatus.PENDING
    return pack


class TestSubmitDecision:
    """POST /api/v1/validation/review-packs/{id}/decisions"""

    @patch("src.api.routes.validation.ReviewerActionsService")
    @patch("src.api.routes.validation.KnowledgeGraphService")
    def test_returns_201_on_confirm(
        self,
        mock_graph_cls: MagicMock,
        mock_service_cls: MagicMock,
    ) -> None:
        pack = _mock_review_pack()
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=pack)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_service = AsyncMock()
        mock_service.submit_decision = AsyncMock(return_value={
            "decision_id": "dec_001",
            "action": "confirm",
            "element_id": "elem_001",
            "graph_write_back": {"new_grade": "B"},
            "decision_at": "2026-02-27T10:00:00Z",
        })
        mock_service_cls.return_value = mock_service

        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/validation/review-packs/{REVIEW_PACK_ID}/decisions",
            json={"element_id": "elem_001", "action": "confirm"},
        )
        assert resp.status_code == 201
        assert resp.json()["action"] == "confirm"
        assert resp.json()["decision_id"] == "dec_001"

    @patch("src.api.routes.validation.KnowledgeGraphService")
    def test_returns_404_for_missing_pack(
        self,
        mock_graph_cls: MagicMock,
    ) -> None:
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/validation/review-packs/{uuid.uuid4()}/decisions",
            json={"element_id": "elem_001", "action": "confirm"},
        )
        assert resp.status_code == 404

    @patch("src.api.routes.validation.ReviewerActionsService")
    @patch("src.api.routes.validation.KnowledgeGraphService")
    def test_returns_201_on_reject(
        self,
        mock_graph_cls: MagicMock,
        mock_service_cls: MagicMock,
    ) -> None:
        pack = _mock_review_pack()
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=pack)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_service = AsyncMock()
        mock_service.submit_decision = AsyncMock(return_value={
            "decision_id": "dec_002",
            "action": "reject",
            "element_id": "elem_002",
            "graph_write_back": {"conflict_id": "cf_001"},
            "decision_at": "2026-02-27T10:00:00Z",
        })
        mock_service_cls.return_value = mock_service

        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/validation/review-packs/{REVIEW_PACK_ID}/decisions",
            json={
                "element_id": "elem_002",
                "action": "reject",
                "payload": {"rejection_reason": "Fabricated"},
            },
        )
        assert resp.status_code == 201
        assert resp.json()["action"] == "reject"

    @patch("src.api.routes.validation.ReviewerActionsService")
    @patch("src.api.routes.validation.KnowledgeGraphService")
    def test_returns_201_on_defer(
        self,
        mock_graph_cls: MagicMock,
        mock_service_cls: MagicMock,
    ) -> None:
        pack = _mock_review_pack()
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=pack)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_service = AsyncMock()
        mock_service.submit_decision = AsyncMock(return_value={
            "decision_id": "dec_003",
            "action": "defer",
            "element_id": "elem_003",
            "graph_write_back": {"deferred_to_dark_room": True},
            "decision_at": "2026-02-27T10:00:00Z",
        })
        mock_service_cls.return_value = mock_service

        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/validation/review-packs/{REVIEW_PACK_ID}/decisions",
            json={"element_id": "elem_003", "action": "defer"},
        )
        assert resp.status_code == 201
        assert resp.json()["action"] == "defer"

    def test_rejects_invalid_action(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/validation/review-packs/{REVIEW_PACK_ID}/decisions",
            json={"element_id": "elem_001", "action": "invalid_action"},
        )
        assert resp.status_code == 422
