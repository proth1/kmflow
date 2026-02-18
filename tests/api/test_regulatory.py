"""Tests for regulatory API routes (policies, controls, regulations)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.models import (
    ComplianceLevel,
    Control,
    ControlEffectiveness,
    Engagement,
    EngagementStatus,
    Policy,
    PolicyType,
    Regulation,
)

# -- Fixtures ----------------------------------------------------------------


@pytest.fixture
def sample_engagement_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_engagement(sample_engagement_id: uuid.UUID) -> Engagement:
    eng = Engagement(
        id=sample_engagement_id,
        name="Test Engagement",
        client="Test Client",
        business_area="Finance",
        status=EngagementStatus.ACTIVE,
    )
    return eng


@pytest.fixture
def sample_policy(sample_engagement_id: uuid.UUID) -> Policy:
    return Policy(
        id=uuid.uuid4(),
        engagement_id=sample_engagement_id,
        name="Data Retention Policy",
        policy_type=PolicyType.ORGANIZATIONAL,
        description="Defines data retention rules",
        clauses={"clause_1": "Retain for 7 years"},
    )


@pytest.fixture
def sample_control(sample_engagement_id: uuid.UUID) -> Control:
    return Control(
        id=uuid.uuid4(),
        engagement_id=sample_engagement_id,
        name="Access Control",
        description="Restricts data access",
        effectiveness=ControlEffectiveness.EFFECTIVE,
        effectiveness_score=0.8,
        linked_policy_ids=[],
    )


@pytest.fixture
def sample_regulation(sample_engagement_id: uuid.UUID) -> Regulation:
    return Regulation(
        id=uuid.uuid4(),
        engagement_id=sample_engagement_id,
        name="GDPR",
        framework="EU General Data Protection Regulation",
        jurisdiction="EU",
        obligations={"article_5": "Data minimization"},
    )


# -- Policy Tests ------------------------------------------------------------


class TestPolicyRoutes:
    """Tests for policy CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_policy(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_engagement: Engagement,
    ) -> None:
        """POST /api/v1/regulatory/policies creates a policy."""
        # Mock engagement lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_engagement
        mock_db_session.execute.return_value = mock_result

        response = await client.post(
            "/api/v1/regulatory/policies",
            json={
                "engagement_id": str(sample_engagement.id),
                "name": "Data Retention Policy",
                "policy_type": "organizational",
                "description": "Defines data retention rules",
            },
        )

        assert response.status_code == 201
        mock_db_session.add.assert_called()
        mock_db_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_policy_engagement_not_found(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """POST /api/v1/regulatory/policies returns 404 for missing engagement."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.post(
            "/api/v1/regulatory/policies",
            json={
                "engagement_id": str(uuid.uuid4()),
                "name": "Test Policy",
                "policy_type": "regulatory",
            },
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_policies(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_policy: Policy,
    ) -> None:
        """GET /api/v1/regulatory/policies returns paginated list."""
        # First call: list query; second call: count query
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_policy]
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value = mock_scalars

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_db_session.execute.side_effect = [mock_list_result, mock_count_result]

        response = await client.get(
            "/api/v1/regulatory/policies",
            params={"engagement_id": str(sample_policy.engagement_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_get_policy(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_policy: Policy,
    ) -> None:
        """GET /api/v1/regulatory/policies/{id} returns a policy."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_policy
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/regulatory/policies/{sample_policy.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Data Retention Policy"

    @pytest.mark.asyncio
    async def test_get_policy_not_found(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """GET /api/v1/regulatory/policies/{id} returns 404 for missing policy."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/regulatory/policies/{uuid.uuid4()}")

        assert response.status_code == 404


# -- Control Tests -----------------------------------------------------------


class TestControlRoutes:
    """Tests for control CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_control(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_engagement: Engagement,
    ) -> None:
        """POST /api/v1/regulatory/controls creates a control."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_engagement
        mock_db_session.execute.return_value = mock_result

        response = await client.post(
            "/api/v1/regulatory/controls",
            json={
                "engagement_id": str(sample_engagement.id),
                "name": "Access Control",
                "effectiveness": "effective",
                "effectiveness_score": 0.8,
            },
        )

        assert response.status_code == 201
        mock_db_session.add.assert_called()

    @pytest.mark.asyncio
    async def test_list_controls(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_control: Control,
    ) -> None:
        """GET /api/v1/regulatory/controls returns paginated list."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_control]
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value = mock_scalars

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_db_session.execute.side_effect = [mock_list_result, mock_count_result]

        response = await client.get(
            "/api/v1/regulatory/controls",
            params={"engagement_id": str(sample_control.engagement_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_get_control(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_control: Control,
    ) -> None:
        """GET /api/v1/regulatory/controls/{id} returns a control."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_control
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/regulatory/controls/{sample_control.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Access Control"


# -- Regulation Tests --------------------------------------------------------


class TestRegulationRoutes:
    """Tests for regulation CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_regulation(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_engagement: Engagement,
    ) -> None:
        """POST /api/v1/regulatory/regulations creates a regulation."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_engagement
        mock_db_session.execute.return_value = mock_result

        response = await client.post(
            "/api/v1/regulatory/regulations",
            json={
                "engagement_id": str(sample_engagement.id),
                "name": "GDPR",
                "framework": "EU GDPR",
                "jurisdiction": "EU",
            },
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_list_regulations(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_regulation: Regulation,
    ) -> None:
        """GET /api/v1/regulatory/regulations returns paginated list."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_regulation]
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value = mock_scalars

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_db_session.execute.side_effect = [mock_list_result, mock_count_result]

        response = await client.get(
            "/api/v1/regulatory/regulations",
            params={"engagement_id": str(sample_regulation.engagement_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_update_regulation(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
        sample_regulation: Regulation,
    ) -> None:
        """PATCH /api/v1/regulatory/regulations/{id} updates fields."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_regulation
        mock_db_session.execute.return_value = mock_result

        response = await client.patch(
            f"/api/v1/regulatory/regulations/{sample_regulation.id}",
            json={"framework": "Updated Framework"},
        )

        assert response.status_code == 200
        mock_db_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_update_regulation_not_found(
        self,
        client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """PATCH /api/v1/regulatory/regulations/{id} returns 404 for missing."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.patch(
            f"/api/v1/regulatory/regulations/{uuid.uuid4()}",
            json={"name": "Updated"},
        )

        assert response.status_code == 404


# -- Model Tests -------------------------------------------------------------


class TestRegulatoryModels:
    """Tests for regulatory model enums and properties."""

    def test_policy_type_values(self) -> None:
        assert PolicyType.ORGANIZATIONAL == "organizational"
        assert PolicyType.REGULATORY == "regulatory"
        assert PolicyType.OPERATIONAL == "operational"
        assert PolicyType.SECURITY == "security"

    def test_control_effectiveness_values(self) -> None:
        assert ControlEffectiveness.HIGHLY_EFFECTIVE == "highly_effective"
        assert ControlEffectiveness.INEFFECTIVE == "ineffective"

    def test_compliance_level_values(self) -> None:
        assert ComplianceLevel.FULLY_COMPLIANT == "fully_compliant"
        assert ComplianceLevel.NOT_ASSESSED == "not_assessed"
