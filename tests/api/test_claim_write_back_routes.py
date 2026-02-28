"""Route-level tests for claim write-back endpoints (Story #324)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

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


def _make_app(mock_session: AsyncMock) -> TestClient:
    app = create_app()
    app.state.neo4j_driver = MagicMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.dependency_overrides[require_engagement_access] = lambda: _mock_user()
    return TestClient(app)


def _mock_claim(
    claim_id: uuid.UUID | None = None,
    engagement_id: uuid.UUID | None = None,
) -> MagicMock:
    claim = MagicMock(spec=SurveyClaim)
    claim.id = claim_id or CLAIM_ID
    claim.engagement_id = engagement_id or ENGAGEMENT_ID
    claim.session_id = uuid.uuid4()
    claim.claim_text = "Test claim"
    claim.probe_type = ProbeType.EXISTENCE
    claim.certainty_tier = CertaintyTier.KNOWN
    claim.respondent_role = "analyst"
    claim.epistemic_frame = None
    return claim


class TestIngestClaim:
    """POST /engagements/{id}/claims/ingest"""

    @patch("src.api.routes.claim_write_back.KnowledgeGraphService")
    @patch("src.api.routes.claim_write_back.ClaimWriteBackService")
    def test_returns_201_on_success(
        self,
        mock_service_cls: MagicMock,
        mock_graph_cls: MagicMock,
    ) -> None:
        claim = _mock_claim()
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=claim)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_service = AsyncMock()
        mock_service.ingest_claim = AsyncMock(return_value={
            "claim_node_id": "abc123",
            "edge_type": "SUPPORTS",
            "conflict_id": None,
            "weight": 1.0,
        })
        mock_service_cls.return_value = mock_service

        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/claims/ingest",
            json={"claim_id": str(claim.id)},
        )
        assert resp.status_code == 201
        assert resp.json()["edge_type"] == "SUPPORTS"

    @patch("src.api.routes.claim_write_back.KnowledgeGraphService")
    def test_returns_404_for_missing_claim(
        self,
        mock_graph_cls: MagicMock,
    ) -> None:
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/claims/ingest",
            json={"claim_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404


class TestBatchIngest:
    """POST /engagements/{id}/claims/batch-ingest"""

    @patch("src.api.routes.claim_write_back.KnowledgeGraphService")
    @patch("src.api.routes.claim_write_back.ClaimWriteBackService")
    def test_returns_201_on_success(
        self,
        mock_service_cls: MagicMock,
        mock_graph_cls: MagicMock,
    ) -> None:
        claims = [_mock_claim(claim_id=uuid.uuid4()), _mock_claim(claim_id=uuid.uuid4())]

        mock_result = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=claims)
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_service = AsyncMock()
        mock_service.batch_ingest_claims = AsyncMock(return_value={
            "claims_ingested": 2,
            "edges_created": 2,
            "conflicts_created": 0,
            "activities_recomputed": 1,
            "recomputation_results": [],
        })
        mock_service_cls.return_value = mock_service

        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/claims/batch-ingest",
            json={"claim_ids": [str(c.id) for c in claims]},
        )
        assert resp.status_code == 201
        assert resp.json()["claims_ingested"] == 2

    @patch("src.api.routes.claim_write_back.KnowledgeGraphService")
    def test_returns_404_for_no_claims(
        self,
        mock_graph_cls: MagicMock,
    ) -> None:
        mock_result = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/claims/batch-ingest",
            json={"claim_ids": [str(uuid.uuid4())]},
        )
        assert resp.status_code == 404


class TestRecomputeConfidence:
    """POST /engagements/{id}/claims/recompute-confidence"""

    @patch("src.api.routes.claim_write_back.KnowledgeGraphService")
    @patch("src.api.routes.claim_write_back.ClaimWriteBackService")
    def test_returns_200_with_result(
        self,
        mock_service_cls: MagicMock,
        mock_graph_cls: MagicMock,
    ) -> None:
        mock_service = AsyncMock()
        mock_service.recompute_activity_confidence = AsyncMock(return_value={
            "activity_id": "act_001",
            "claim_count": 5,
            "aggregate_weight": 4.0,
            "claim_confidence": 0.8,
        })
        mock_service_cls.return_value = mock_service

        mock_session = AsyncMock()
        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/claims/recompute-confidence",
            json={"activity_id": "act_001"},
        )
        assert resp.status_code == 200
        assert resp.json()["claim_confidence"] == 0.8
