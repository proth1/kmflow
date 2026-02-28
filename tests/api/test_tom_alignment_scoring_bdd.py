"""BDD tests for Story #348 — Automated TOM Alignment Scoring Across 6 Dimensions.

Scenario 1: Alignment Score Computed Per Process Element Per Dimension
Scenario 2: FULL_GAP Detected for Activity Without TOM Counterpart
Scenario 3: PARTIAL_GAP with Deviation Score for Near-Match
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.core.auth import get_current_user
from src.core.models import (
    AlignmentRunStatus,
    TOMDimension,
    TOMGapType,
    User,
    UserRole,
)
from src.tom.alignment_scoring import (
    AlignmentScoringService,
    classify_similarity,
    cosine_similarity,
)

APP = create_app()

ENGAGEMENT_ID = uuid.uuid4()
TOM_ID = uuid.uuid4()
RUN_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user() -> User:
    u = MagicMock(spec=User)
    u.id = USER_ID
    u.role = UserRole.PLATFORM_ADMIN
    return u


def _make_plain_mock(**kwargs: Any) -> MagicMock:
    """Create a MagicMock that stores kwargs as regular attributes."""
    m = MagicMock()
    if "id" not in kwargs:
        m.id = uuid.uuid4()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


def _make_app_with_session(mock_session: AsyncMock) -> Any:
    """Create app with overridden dependencies."""
    from src.api.deps import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    return app


# ---------------------------------------------------------------------------
# Unit tests for scoring utilities
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    """Tests for the cosine_similarity function."""

    def test_identical_vectors(self) -> None:
        vec = [1.0, 0.5, 0.3]
        result = cosine_similarity(vec, vec)
        assert abs(result - 1.0) < 1e-6

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        result = cosine_similarity(a, b)
        assert abs(result) < 1e-6

    def test_zero_vector(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_similar_vectors(self) -> None:
        a = [1.0, 0.8, 0.6]
        b = [0.9, 0.7, 0.5]
        result = cosine_similarity(a, b)
        assert result > 0.99


class TestClassifySimilarity:
    """Tests for the classify_similarity function."""

    def test_no_gap_high_similarity(self) -> None:
        gap_type, deviation = classify_similarity(0.90)
        assert gap_type == TOMGapType.NO_GAP
        assert deviation == 0.0

    def test_no_gap_at_threshold(self) -> None:
        gap_type, deviation = classify_similarity(0.85)
        assert gap_type == TOMGapType.NO_GAP
        assert deviation == 0.0

    def test_partial_gap(self) -> None:
        gap_type, deviation = classify_similarity(0.62)
        assert gap_type == TOMGapType.PARTIAL_GAP
        assert abs(deviation - 0.38) < 1e-4

    def test_partial_gap_at_lower_threshold(self) -> None:
        gap_type, deviation = classify_similarity(0.40)
        assert gap_type == TOMGapType.PARTIAL_GAP
        assert abs(deviation - 0.60) < 1e-4

    def test_full_gap_below_threshold(self) -> None:
        gap_type, deviation = classify_similarity(0.39)
        assert gap_type == TOMGapType.FULL_GAP
        assert deviation == 1.0

    def test_full_gap_zero(self) -> None:
        gap_type, deviation = classify_similarity(0.0)
        assert gap_type == TOMGapType.FULL_GAP
        assert deviation == 1.0


# ---------------------------------------------------------------------------
# Unit tests for AlignmentScoringService._score_single
# ---------------------------------------------------------------------------


class TestScoreSingle:
    """Tests for the _score_single method."""

    def _make_activity(self, name: str = "Test Activity") -> MagicMock:
        act = _make_plain_mock()
        act.name = name
        return act

    def test_graph_alignment_returns_no_gap(self) -> None:
        """Activity with ALIGNS_TO edge → NO_GAP."""
        service = AlignmentScoringService(graph_service=MagicMock())
        activity = self._make_activity("Review Credit Risk")
        aligned_pairs = {(str(activity.id), TOMDimension.PROCESS_ARCHITECTURE)}

        score = service._score_single(
            activity=activity,
            dimension=TOMDimension.PROCESS_ARCHITECTURE,
            aligned_pairs=aligned_pairs,
            activity_emb=None,
            dim_emb=None,
            dim_description=None,
        )

        assert score.gap_type == TOMGapType.NO_GAP
        assert score.deviation_score == 0.0
        assert score.alignment_evidence["method"] == "graph_alignment"

    def test_embedding_no_gap(self) -> None:
        """High embedding similarity → NO_GAP."""
        service = AlignmentScoringService(graph_service=MagicMock())
        activity = self._make_activity("Automated Credit Scoring")

        # Create two nearly identical vectors
        emb = [0.5] * 10
        score = service._score_single(
            activity=activity,
            dimension=TOMDimension.PROCESS_ARCHITECTURE,
            aligned_pairs=set(),
            activity_emb=emb,
            dim_emb=emb,  # identical → similarity=1.0
            dim_description="Automated Credit Scoring",
        )

        assert score.gap_type == TOMGapType.NO_GAP
        assert score.deviation_score == 0.0

    def test_embedding_partial_gap(self) -> None:
        """Medium embedding similarity → PARTIAL_GAP."""
        service = AlignmentScoringService(graph_service=MagicMock())
        activity = self._make_activity("Credit Risk Assessment")

        # Construct vectors with known cosine similarity ~0.62
        a = [1.0, 0.5, 0.0, 0.3, 0.8]
        b = [0.4, 0.9, 0.7, 0.1, 0.2]
        sim = cosine_similarity(a, b)
        # Verify these give a partial gap range
        assert 0.4 <= sim < 0.85

        score = service._score_single(
            activity=activity,
            dimension=TOMDimension.PROCESS_ARCHITECTURE,
            aligned_pairs=set(),
            activity_emb=a,
            dim_emb=b,
            dim_description="Automated Credit Scoring",
        )

        assert score.gap_type == TOMGapType.PARTIAL_GAP
        assert 0.0 < score.deviation_score < 1.0
        assert score.alignment_evidence["method"] == "embedding_similarity"

    def test_embedding_full_gap(self) -> None:
        """Low embedding similarity → FULL_GAP."""
        service = AlignmentScoringService(graph_service=MagicMock())
        activity = self._make_activity("Manual Exception Logging")

        # Nearly orthogonal vectors → low similarity
        a = [1.0, 0.0, 0.0, 0.0, 0.0]
        b = [0.0, 0.0, 0.0, 0.0, 1.0]

        score = service._score_single(
            activity=activity,
            dimension=TOMDimension.TECHNOLOGY_AND_DATA,
            aligned_pairs=set(),
            activity_emb=a,
            dim_emb=b,
            dim_description="Real-time monitoring system",
        )

        assert score.gap_type == TOMGapType.FULL_GAP
        assert score.deviation_score == 1.0

    def test_no_data_returns_full_gap(self) -> None:
        """No graph edge and no embeddings → FULL_GAP."""
        service = AlignmentScoringService(graph_service=MagicMock())
        activity = self._make_activity("Manual Exception Logging")

        score = service._score_single(
            activity=activity,
            dimension=TOMDimension.RISK_AND_COMPLIANCE,
            aligned_pairs=set(),
            activity_emb=None,
            dim_emb=None,
            dim_description=None,
        )

        assert score.gap_type == TOMGapType.FULL_GAP
        assert score.deviation_score == 1.0
        assert score.alignment_evidence["method"] == "no_data"


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestTriggerAlignmentScoring:
    """Scenario 1: POST /api/v1/tom/scoring/{engagement_id}/run"""

    @pytest.mark.asyncio
    async def test_trigger_returns_202_with_run_id(self) -> None:
        """Given a POV and TOM exist, When POST /scoring/{id}/run, Then 202 with run_id."""
        mock_session = AsyncMock()

        # First call: engagement lookup → found
        eng = _make_plain_mock(id=ENGAGEMENT_ID)
        eng_result = MagicMock()
        eng_result.scalar_one_or_none.return_value = eng

        # Second call: TOM lookup → found
        tom = _make_plain_mock(id=TOM_ID, engagement_id=ENGAGEMENT_ID)
        tom_result = MagicMock()
        tom_result.scalar_one_or_none.return_value = tom

        # Third call: duplicate run check → none found
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(side_effect=[eng_result, tom_result, dup_result])
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()

        app = _make_app_with_session(mock_session)

        # Set app.state attributes needed by background task
        app.state.db_session_factory = MagicMock()
        app.state.neo4j_driver = MagicMock()

        # Don't patch TOMAlignmentRun (SA needs it for select queries).
        # Track the added object and set its id on flush (simulating SA default).
        _added_objects: list[Any] = []

        def _fake_add(obj: Any) -> None:
            _added_objects.append(obj)

        mock_session.add = _fake_add

        async def _fake_flush() -> None:
            for obj in _added_objects:
                if getattr(obj, "id", None) is None:
                    obj.id = uuid.uuid4()

        mock_session.flush = _fake_flush

        with (
            mock.patch("src.api.routes.tom.asyncio") as mock_asyncio,
            mock.patch("src.api.routes.tom.log_audit", new_callable=AsyncMock),
        ):
            mock_task = MagicMock()
            mock_asyncio.create_task.return_value = mock_task

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    f"/api/v1/tom/scoring/{ENGAGEMENT_ID}/run?tom_id={TOM_ID}",
                )

        assert resp.status_code == 202
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "pending"
        assert data["message"] == "Alignment scoring started"

    @pytest.mark.asyncio
    async def test_trigger_404_engagement_not_found(self) -> None:
        """Returns 404 when engagement does not exist."""
        mock_session = AsyncMock()

        eng_result = MagicMock()
        eng_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=eng_result)

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                f"/api/v1/tom/scoring/{ENGAGEMENT_ID}/run?tom_id={TOM_ID}",
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_trigger_404_tom_not_found(self) -> None:
        """Returns 404 when TOM does not exist for engagement."""
        mock_session = AsyncMock()

        eng = _make_plain_mock(id=ENGAGEMENT_ID)
        eng_result = MagicMock()
        eng_result.scalar_one_or_none.return_value = eng

        tom_result = MagicMock()
        tom_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(side_effect=[eng_result, tom_result])

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                f"/api/v1/tom/scoring/{ENGAGEMENT_ID}/run?tom_id={TOM_ID}",
            )

        assert resp.status_code == 404


class TestGetAlignmentRunResults:
    """Scenario 1-3: GET /api/v1/tom/scoring/runs/{run_id}/results"""

    @pytest.mark.asyncio
    async def test_get_results_paginated(self) -> None:
        """Returns paginated alignment results."""
        mock_session = AsyncMock()

        # First call: fetch TOMAlignmentRun
        run = _make_plain_mock(
            id=RUN_ID,
            engagement_id=ENGAGEMENT_ID,
            status=AlignmentRunStatus.COMPLETE,
        )
        run_result = MagicMock()
        run_result.scalar_one_or_none.return_value = run

        # Second call (engagement member check): admin bypasses
        # Third call: count → 3
        count_result = MagicMock()
        count_result.scalar.return_value = 3

        # Fourth call: fetch results
        result_items = []
        for _i in range(3):
            r = _make_plain_mock(
                id=uuid.uuid4(),
                activity_id=uuid.uuid4(),
                dimension_type=TOMDimension.PROCESS_ARCHITECTURE,
                gap_type=TOMGapType.NO_GAP,
                deviation_score=0.0,
                alignment_evidence={"method": "graph_alignment"},
            )
            result_items.append(r)

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = result_items

        mock_session.execute = AsyncMock(side_effect=[run_result, count_result, items_result])

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/api/v1/tom/scoring/runs/{RUN_ID}/results?limit=10&offset=0",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == str(RUN_ID)
        assert data["status"] == "complete"
        assert data["total"] == 3
        assert len(data["items"]) == 3

    @pytest.mark.asyncio
    async def test_get_results_404_run_not_found(self) -> None:
        """Returns 404 when run does not exist."""
        mock_session = AsyncMock()

        run_result = MagicMock()
        run_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=run_result)

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/api/v1/tom/scoring/runs/{RUN_ID}/results",
            )

        assert resp.status_code == 404


class TestScenario2FullGapDetection:
    """Scenario 2: FULL_GAP for activity without TOM counterpart."""

    def test_full_gap_no_embedding_no_graph(self) -> None:
        """Activity with no graph edge and no embedding → FULL_GAP, deviation=1.0."""
        service = AlignmentScoringService(graph_service=MagicMock())
        activity = _make_plain_mock()
        activity.name = "Manual Exception Logging"

        score = service._score_single(
            activity=activity,
            dimension=TOMDimension.TECHNOLOGY_AND_DATA,
            aligned_pairs=set(),
            activity_emb=None,
            dim_emb=None,
            dim_description=None,
        )

        assert score.gap_type == TOMGapType.FULL_GAP
        assert score.deviation_score == 1.0
        assert score.activity_name == "Manual Exception Logging"

    def test_full_gap_low_embedding_similarity(self) -> None:
        """Activity below 0.4 threshold → FULL_GAP, deviation=1.0."""
        service = AlignmentScoringService(graph_service=MagicMock())
        activity = _make_plain_mock()
        activity.name = "Manual Exception Logging"

        # Orthogonal vectors → similarity ≈ 0
        a = [1.0, 0.0, 0.0]
        b = [0.0, 0.0, 1.0]

        score = service._score_single(
            activity=activity,
            dimension=TOMDimension.TECHNOLOGY_AND_DATA,
            aligned_pairs=set(),
            activity_emb=a,
            dim_emb=b,
            dim_description="Automated monitoring platform",
        )

        assert score.gap_type == TOMGapType.FULL_GAP
        assert score.deviation_score == 1.0


class TestScenario3PartialGap:
    """Scenario 3: PARTIAL_GAP with deviation score for near-match."""

    def test_partial_gap_with_known_similarity(self) -> None:
        """Similarity 0.62 → PARTIAL_GAP with deviation_score = 0.38."""
        service = AlignmentScoringService(graph_service=MagicMock())
        activity = _make_plain_mock()
        activity.name = "Credit Risk Assessment"

        # Construct vectors with cosine similarity ~0.62
        # Use vectors that we can verify
        a = [1.0, 0.5, 0.0, 0.3, 0.8]
        b = [0.4, 0.9, 0.7, 0.1, 0.2]
        actual_sim = cosine_similarity(a, b)
        assert 0.4 <= actual_sim < 0.85, f"Expected partial gap range, got {actual_sim}"

        score = service._score_single(
            activity=activity,
            dimension=TOMDimension.PROCESS_ARCHITECTURE,
            aligned_pairs=set(),
            activity_emb=a,
            dim_emb=b,
            dim_description="Automated Credit Scoring",
        )

        assert score.gap_type == TOMGapType.PARTIAL_GAP
        assert 0.0 < score.deviation_score < 1.0
        expected_deviation = round(1.0 - actual_sim, 4)
        assert abs(score.deviation_score - expected_deviation) < 1e-4
        assert score.alignment_evidence["method"] == "embedding_similarity"
        assert "similarity_score" in score.alignment_evidence
        assert score.alignment_evidence["tom_specification"] == "Automated Credit Scoring"
        assert score.alignment_evidence["activity_description"] == "Credit Risk Assessment"

    def test_partial_gap_evidence_includes_descriptions(self) -> None:
        """Alignment evidence references TOM specification and activity description."""
        service = AlignmentScoringService(graph_service=MagicMock())
        activity = _make_plain_mock()
        activity.name = "Invoice Processing"

        # Vectors with partial similarity
        a = [0.8, 0.6, 0.4, 0.2]
        b = [0.3, 0.7, 0.5, 0.9]
        sim = cosine_similarity(a, b)
        assert 0.4 <= sim < 0.85

        score = service._score_single(
            activity=activity,
            dimension=TOMDimension.GOVERNANCE_STRUCTURES,
            aligned_pairs=set(),
            activity_emb=a,
            dim_emb=b,
            dim_description="Automated invoice reconciliation",
        )

        assert score.gap_type == TOMGapType.PARTIAL_GAP
        evidence = score.alignment_evidence
        assert evidence["activity_description"] == "Invoice Processing"
        assert evidence["tom_specification"] == "Automated invoice reconciliation"
        assert isinstance(evidence["similarity_score"], float)
