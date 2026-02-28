"""BDD tests for Gap Analysis Dashboard API endpoint (Story #347).

Tests the aggregated gap analysis dashboard with gap counts by type/severity,
TOM dimension alignment scores, prioritized recommendations, and maturity heatmap.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.routes.tom import (
    DimensionAlignmentScore,
    GapCountByType,
    GapDashboardResponse,
    RecommendationEntry,
    get_gap_analysis_dashboard,
)
from src.core.models import TOMDimension, TOMGapType, UserRole

# -- Fixtures ----------------------------------------------------------------


def _make_mock_user(role: UserRole = UserRole.PLATFORM_ADMIN) -> MagicMock:
    """Create a mock user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


def _make_mock_gap(
    engagement_id: uuid.UUID,
    gap_type: TOMGapType = TOMGapType.FULL_GAP,
    dimension: TOMDimension = TOMDimension.PROCESS_ARCHITECTURE,
    severity: float = 0.8,
    confidence: float = 0.7,
    recommendation: str | None = "Redesign the process to align with target",
    rationale: str | None = "Current state deviates significantly",
) -> MagicMock:
    """Create a mock GapAnalysisResult."""
    gap = MagicMock()
    gap.id = uuid.uuid4()
    gap.engagement_id = engagement_id
    gap.gap_type = gap_type
    gap.dimension = dimension
    gap.severity = severity
    gap.confidence = confidence
    gap.recommendation = recommendation
    gap.rationale = rationale
    gap.priority_score = round(severity * confidence, 4)
    return gap


def _make_mock_maturity(
    engagement_id: uuid.UUID,
    maturity_level: str = "optimized",
    level_number: int = 5,
) -> MagicMock:
    """Create a mock MaturityScore."""
    score = MagicMock()
    score.id = uuid.uuid4()
    score.engagement_id = engagement_id
    score.maturity_level = maturity_level
    score.level_number = level_number
    return score


# ============================================================
# Scenario 1: Gap counts displayed by type and severity
# ============================================================


class TestGapCountsByTypeAndSeverity:
    """GET /api/v1/tom/dashboard/{id}/gap-analysis returns gap counts
    broken down by type and severity."""

    @pytest.mark.asyncio
    async def test_returns_gap_counts_by_type(self) -> None:
        """Gap counts are broken down by type: FULL_GAP, PARTIAL_GAP, DEVIATION."""
        eng_id = uuid.uuid4()

        gaps = [
            _make_mock_gap(eng_id, TOMGapType.FULL_GAP, severity=0.95),
            _make_mock_gap(eng_id, TOMGapType.FULL_GAP, severity=0.75),
            _make_mock_gap(eng_id, TOMGapType.PARTIAL_GAP, severity=0.5),
            _make_mock_gap(eng_id, TOMGapType.DEVIATION, severity=0.3),
        ]

        session = AsyncMock()
        gap_result = MagicMock()
        gap_result.scalars.return_value.all.return_value = gaps
        maturity_result = MagicMock()
        maturity_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[gap_result, maturity_result])
        user = _make_mock_user()

        result = await get_gap_analysis_dashboard(eng_id, session, user)

        assert result["total_gaps"] == 4

        counts_by_type = {c["gap_type"]: c for c in result["gap_counts"]}
        assert counts_by_type["full_gap"]["total"] == 2
        assert counts_by_type["partial_gap"]["total"] == 1
        assert counts_by_type["deviation"]["total"] == 1

    @pytest.mark.asyncio
    async def test_severity_breakdown(self) -> None:
        """Each type is further broken down by severity buckets."""
        eng_id = uuid.uuid4()

        gaps = [
            _make_mock_gap(eng_id, TOMGapType.FULL_GAP, severity=0.95),  # critical
            _make_mock_gap(eng_id, TOMGapType.FULL_GAP, severity=0.75),  # high
            _make_mock_gap(eng_id, TOMGapType.FULL_GAP, severity=0.5),   # medium
            _make_mock_gap(eng_id, TOMGapType.FULL_GAP, severity=0.2),   # low
        ]

        session = AsyncMock()
        gap_result = MagicMock()
        gap_result.scalars.return_value.all.return_value = gaps
        maturity_result = MagicMock()
        maturity_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[gap_result, maturity_result])
        user = _make_mock_user()

        result = await get_gap_analysis_dashboard(eng_id, session, user)

        full_gap = next(c for c in result["gap_counts"] if c["gap_type"] == "full_gap")
        assert full_gap["critical"] == 1
        assert full_gap["high"] == 1
        assert full_gap["medium"] == 1
        assert full_gap["low"] == 1

    @pytest.mark.asyncio
    async def test_no_gaps_returns_zero_counts(self) -> None:
        """Engagement with no gaps returns zero counts."""
        eng_id = uuid.uuid4()

        session = AsyncMock()
        gap_result = MagicMock()
        gap_result.scalars.return_value.all.return_value = []
        maturity_result = MagicMock()
        maturity_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[gap_result, maturity_result])
        user = _make_mock_user()

        result = await get_gap_analysis_dashboard(eng_id, session, user)

        assert result["total_gaps"] == 0
        for count in result["gap_counts"]:
            assert count["total"] == 0

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self) -> None:
        """Non-member user gets 403 Forbidden."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        session = AsyncMock()
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=member_result)
        user = _make_mock_user(role=UserRole.ENGAGEMENT_LEAD)

        with pytest.raises(HTTPException) as exc_info:
            await get_gap_analysis_dashboard(eng_id, session, user)

        assert exc_info.value.status_code == 403


# ============================================================
# Scenario 2: TOM alignment radar chart data
# ============================================================


class TestDimensionAlignmentScores:
    """Dimension alignment scores for the radar chart."""

    @pytest.mark.asyncio
    async def test_returns_scores_per_dimension(self) -> None:
        """Each TOM dimension gets an alignment score."""
        eng_id = uuid.uuid4()

        gaps = [
            _make_mock_gap(eng_id, dimension=TOMDimension.PROCESS_ARCHITECTURE, confidence=0.8),
            _make_mock_gap(eng_id, dimension=TOMDimension.PROCESS_ARCHITECTURE, confidence=0.6),
            _make_mock_gap(eng_id, dimension=TOMDimension.PEOPLE_AND_ORGANIZATION, confidence=0.4),
        ]

        session = AsyncMock()
        gap_result = MagicMock()
        gap_result.scalars.return_value.all.return_value = gaps
        maturity_result = MagicMock()
        maturity_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[gap_result, maturity_result])
        user = _make_mock_user()

        result = await get_gap_analysis_dashboard(eng_id, session, user)

        scores_by_dim = {s["dimension"]: s for s in result["dimension_scores"]}
        assert len(scores_by_dim) == len(TOMDimension)

        pa_score = scores_by_dim["process_architecture"]
        assert pa_score["score"] == 0.7  # (0.8 + 0.6) / 2

        po_score = scores_by_dim["people_and_organization"]
        assert po_score["score"] == 0.4

    @pytest.mark.asyncio
    async def test_dimensions_below_threshold_flagged(self) -> None:
        """Dimensions scoring below 60% are flagged."""
        eng_id = uuid.uuid4()

        gaps = [
            _make_mock_gap(eng_id, dimension=TOMDimension.TECHNOLOGY_AND_DATA, confidence=0.3),
        ]

        session = AsyncMock()
        gap_result = MagicMock()
        gap_result.scalars.return_value.all.return_value = gaps
        maturity_result = MagicMock()
        maturity_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[gap_result, maturity_result])
        user = _make_mock_user()

        result = await get_gap_analysis_dashboard(eng_id, session, user)

        td_score = next(s for s in result["dimension_scores"] if s["dimension"] == "technology_and_data")
        assert td_score["below_threshold"] is True

    @pytest.mark.asyncio
    async def test_no_gaps_dimension_scores_default_to_full(self) -> None:
        """Dimensions with no gaps default to 1.0 (fully aligned)."""
        eng_id = uuid.uuid4()

        session = AsyncMock()
        gap_result = MagicMock()
        gap_result.scalars.return_value.all.return_value = []
        maturity_result = MagicMock()
        maturity_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[gap_result, maturity_result])
        user = _make_mock_user()

        result = await get_gap_analysis_dashboard(eng_id, session, user)

        for score in result["dimension_scores"]:
            assert score["score"] == 1.0
            assert score["below_threshold"] is False


# ============================================================
# Scenario 3: Recommendations sorted by priority score
# ============================================================


class TestPrioritizedRecommendations:
    """Recommendations are sorted by priority_score descending."""

    @pytest.mark.asyncio
    async def test_recommendations_sorted_by_priority(self) -> None:
        """Recommendations are sorted in descending order by priority_score."""
        eng_id = uuid.uuid4()

        gaps = [
            _make_mock_gap(eng_id, severity=0.3, confidence=0.3),  # priority = 0.09
            _make_mock_gap(eng_id, severity=0.9, confidence=0.9),  # priority = 0.81
            _make_mock_gap(eng_id, severity=0.5, confidence=0.5),  # priority = 0.25
        ]

        session = AsyncMock()
        gap_result = MagicMock()
        gap_result.scalars.return_value.all.return_value = gaps
        maturity_result = MagicMock()
        maturity_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[gap_result, maturity_result])
        user = _make_mock_user()

        result = await get_gap_analysis_dashboard(eng_id, session, user)

        scores = [r["priority_score"] for r in result["recommendations"]]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_recommendation_includes_all_fields(self) -> None:
        """Each recommendation includes gap type, severity, dimension, etc."""
        eng_id = uuid.uuid4()

        gap = _make_mock_gap(
            eng_id,
            gap_type=TOMGapType.PARTIAL_GAP,
            dimension=TOMDimension.GOVERNANCE_STRUCTURES,
            severity=0.8,
            confidence=0.7,
            recommendation="Implement governance framework",
            rationale="Missing governance controls",
        )

        session = AsyncMock()
        gap_result = MagicMock()
        gap_result.scalars.return_value.all.return_value = [gap]
        maturity_result = MagicMock()
        maturity_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[gap_result, maturity_result])
        user = _make_mock_user()

        result = await get_gap_analysis_dashboard(eng_id, session, user)

        rec = result["recommendations"][0]
        assert rec["gap_type"] == "partial_gap"
        assert rec["dimension"] == "governance_structures"
        assert rec["severity"] == 0.8
        assert rec["priority_score"] == 0.56
        assert "governance framework" in rec["recommendation"]
        assert "governance controls" in rec["rationale"]

    @pytest.mark.asyncio
    async def test_recommendation_title_truncated(self) -> None:
        """Recommendation title is truncated to 80 chars."""
        eng_id = uuid.uuid4()

        long_rec = "X" * 120
        gap = _make_mock_gap(eng_id, recommendation=long_rec)

        session = AsyncMock()
        gap_result = MagicMock()
        gap_result.scalars.return_value.all.return_value = [gap]
        maturity_result = MagicMock()
        maturity_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[gap_result, maturity_result])
        user = _make_mock_user()

        result = await get_gap_analysis_dashboard(eng_id, session, user)

        assert len(result["recommendations"][0]["title"]) == 80

    @pytest.mark.asyncio
    async def test_no_recommendation_uses_fallback_title(self) -> None:
        """Gaps without recommendation use a fallback title."""
        eng_id = uuid.uuid4()

        gap = _make_mock_gap(eng_id, recommendation=None)

        session = AsyncMock()
        gap_result = MagicMock()
        gap_result.scalars.return_value.all.return_value = [gap]
        maturity_result = MagicMock()
        maturity_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[gap_result, maturity_result])
        user = _make_mock_user()

        result = await get_gap_analysis_dashboard(eng_id, session, user)

        title = result["recommendations"][0]["title"]
        assert "full_gap" in title
        assert "process_architecture" in title


# ============================================================
# Maturity heatmap
# ============================================================


class TestMaturityHeatmap:
    """Maturity heatmap data for the dashboard."""

    @pytest.mark.asyncio
    async def test_returns_maturity_heatmap(self) -> None:
        """Maturity heatmap is included in the response."""
        eng_id = uuid.uuid4()

        session = AsyncMock()
        gap_result = MagicMock()
        gap_result.scalars.return_value.all.return_value = []
        maturity_result = MagicMock()
        maturity_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[gap_result, maturity_result])
        user = _make_mock_user()

        result = await get_gap_analysis_dashboard(eng_id, session, user)

        assert "maturity_heatmap" in result
        assert isinstance(result["maturity_heatmap"], dict)
        # All TOM dimensions present as keys
        for dim in TOMDimension:
            assert dim.value in result["maturity_heatmap"]


# ============================================================
# Schema validation tests
# ============================================================


class TestGapDashboardSchemas:
    """Schema validation for gap analysis dashboard response models."""

    def test_gap_count_by_type_validates(self) -> None:
        """GapCountByType schema is valid."""
        entry = GapCountByType(
            gap_type="full_gap",
            total=5,
            critical=1,
            high=2,
            medium=1,
            low=1,
        )
        assert entry.total == 5

    def test_dimension_alignment_score_validates(self) -> None:
        """DimensionAlignmentScore schema is valid."""
        entry = DimensionAlignmentScore(
            dimension="process_architecture",
            score=0.75,
            below_threshold=False,
        )
        assert entry.score == 0.75

    def test_recommendation_entry_validates(self) -> None:
        """RecommendationEntry schema is valid."""
        entry = RecommendationEntry(
            gap_id="gap-1",
            title="Implement governance",
            gap_type="partial_gap",
            dimension="governance_structures",
            severity=0.8,
            priority_score=0.56,
            recommendation="Implement governance framework",
            rationale="Missing controls",
        )
        assert entry.priority_score == 0.56

    def test_gap_dashboard_response_validates(self) -> None:
        """GapDashboardResponse schema is valid."""
        resp = GapDashboardResponse(
            engagement_id="eng-1",
            total_gaps=0,
            gap_counts=[],
            dimension_scores=[],
            recommendations=[],
            maturity_heatmap={},
        )
        assert resp.total_gaps == 0
