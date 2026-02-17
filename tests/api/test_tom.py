"""Tests for TOM API routes (models, gaps, best practices, benchmarks)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.models import (
    Benchmark,
    BestPractice,
    Engagement,
    EngagementStatus,
    GapAnalysisResult,
    ProcessMaturity,
    TargetOperatingModel,
    TOMDimension,
    TOMGapType,
)


# -- Fixtures ----------------------------------------------------------------


@pytest.fixture
def sample_engagement_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_engagement(sample_engagement_id: uuid.UUID) -> Engagement:
    return Engagement(
        id=sample_engagement_id,
        name="Test Engagement",
        client="Test Client",
        business_area="Operations",
        status=EngagementStatus.ACTIVE,
    )


@pytest.fixture
def sample_tom(sample_engagement_id: uuid.UUID) -> TargetOperatingModel:
    return TargetOperatingModel(
        id=uuid.uuid4(),
        engagement_id=sample_engagement_id,
        name="Digital TOM",
        dimensions={"process_architecture": {"target": "defined"}},
        maturity_targets={"process_architecture": "defined"},
    )


@pytest.fixture
def sample_gap(sample_engagement_id: uuid.UUID, sample_tom: TargetOperatingModel) -> GapAnalysisResult:
    return GapAnalysisResult(
        id=uuid.uuid4(),
        engagement_id=sample_engagement_id,
        tom_id=sample_tom.id,
        gap_type=TOMGapType.PARTIAL_GAP,
        dimension=TOMDimension.PROCESS_ARCHITECTURE,
        severity=0.7,
        confidence=0.85,
        rationale="Process documentation incomplete",
        recommendation="Complete process mapping",
    )


# -- TOM Model Tests ---------------------------------------------------------


class TestTOMRoutes:
    """Tests for TOM CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_tom(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_engagement: Engagement,
    ) -> None:
        """POST /api/v1/tom/models creates a TOM."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_engagement
        mock_db_session.execute.return_value = mock_result

        response = await client.post(
            "/api/v1/tom/models",
            json={
                "engagement_id": str(sample_engagement.id),
                "name": "Digital TOM",
                "dimensions": {"process_architecture": {"target": "defined"}},
            },
        )

        assert response.status_code == 201
        mock_db_session.add.assert_called()
        mock_db_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_tom_engagement_not_found(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """POST /api/v1/tom/models returns 404 for missing engagement."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.post(
            "/api/v1/tom/models",
            json={
                "engagement_id": str(uuid.uuid4()),
                "name": "Test TOM",
            },
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_toms(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_tom: TargetOperatingModel,
    ) -> None:
        """GET /api/v1/tom/models returns paginated list."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_tom]
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value = mock_scalars

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_db_session.execute.side_effect = [mock_list_result, mock_count_result]

        response = await client.get(
            "/api/v1/tom/models",
            params={"engagement_id": str(sample_tom.engagement_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_get_tom(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_tom: TargetOperatingModel,
    ) -> None:
        """GET /api/v1/tom/models/{id} returns a TOM."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_tom
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/tom/models/{sample_tom.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Digital TOM"

    @pytest.mark.asyncio
    async def test_get_tom_not_found(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """GET /api/v1/tom/models/{id} returns 404 for missing TOM."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/tom/models/{uuid.uuid4()}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_tom(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_tom: TargetOperatingModel,
    ) -> None:
        """PATCH /api/v1/tom/models/{id} updates a TOM."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_tom
        mock_db_session.execute.return_value = mock_result

        response = await client.patch(
            f"/api/v1/tom/models/{sample_tom.id}",
            json={"name": "Updated TOM"},
        )

        assert response.status_code == 200
        mock_db_session.commit.assert_awaited()


# -- Gap Analysis Tests ------------------------------------------------------


class TestGapRoutes:
    """Tests for gap analysis result endpoints."""

    @pytest.mark.asyncio
    async def test_create_gap(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_engagement: Engagement,
        sample_tom: TargetOperatingModel,
    ) -> None:
        """POST /api/v1/tom/gaps creates a gap result."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_engagement
        mock_db_session.execute.return_value = mock_result

        response = await client.post(
            "/api/v1/tom/gaps",
            json={
                "engagement_id": str(sample_engagement.id),
                "tom_id": str(sample_tom.id),
                "gap_type": "partial_gap",
                "dimension": "process_architecture",
                "severity": 0.7,
                "confidence": 0.85,
                "rationale": "Process docs incomplete",
            },
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_list_gaps(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_gap: GapAnalysisResult,
    ) -> None:
        """GET /api/v1/tom/gaps returns paginated list."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_gap]
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value = mock_scalars

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_db_session.execute.side_effect = [mock_list_result, mock_count_result]

        response = await client.get(
            "/api/v1/tom/gaps",
            params={"engagement_id": str(sample_gap.engagement_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1


# -- Best Practice Tests -----------------------------------------------------


class TestBestPracticeRoutes:
    """Tests for best practice endpoints."""

    @pytest.mark.asyncio
    async def test_create_best_practice(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """POST /api/v1/tom/best-practices creates an entry."""
        response = await client.post(
            "/api/v1/tom/best-practices",
            json={
                "domain": "Financial Services",
                "industry": "Banking",
                "description": "Automated KYC verification",
                "tom_dimension": "technology_and_data",
            },
        )

        assert response.status_code == 201
        mock_db_session.add.assert_called()


# -- Benchmark Tests ---------------------------------------------------------


class TestBenchmarkRoutes:
    """Tests for benchmark endpoints."""

    @pytest.mark.asyncio
    async def test_create_benchmark(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """POST /api/v1/tom/benchmarks creates an entry."""
        response = await client.post(
            "/api/v1/tom/benchmarks",
            json={
                "metric_name": "Process Cycle Time",
                "industry": "Banking",
                "p25": 2.0,
                "p50": 5.0,
                "p75": 10.0,
                "p90": 20.0,
            },
        )

        assert response.status_code == 201
        mock_db_session.add.assert_called()


# -- Model Tests -------------------------------------------------------------


class TestTOMModels:
    """Tests for TOM model enums and computed properties."""

    def test_tom_dimension_values(self) -> None:
        assert TOMDimension.PROCESS_ARCHITECTURE == "process_architecture"
        assert TOMDimension.RISK_AND_COMPLIANCE == "risk_and_compliance"

    def test_tom_gap_type_values(self) -> None:
        assert TOMGapType.FULL_GAP == "full_gap"
        assert TOMGapType.NO_GAP == "no_gap"

    def test_process_maturity_values(self) -> None:
        assert ProcessMaturity.INITIAL == "initial"
        assert ProcessMaturity.OPTIMIZING == "optimizing"

    def test_gap_priority_score(self) -> None:
        gap = GapAnalysisResult(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            tom_id=uuid.uuid4(),
            gap_type=TOMGapType.FULL_GAP,
            dimension=TOMDimension.PROCESS_ARCHITECTURE,
            severity=0.8,
            confidence=0.9,
        )
        assert gap.priority_score == 0.72
