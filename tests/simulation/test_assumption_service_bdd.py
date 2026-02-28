"""BDD tests for Financial Assumption Management (Story #354).

Tests the 5 acceptance scenarios:
1. Creation stores all required fields
2. Range-bearing assumption stores confidence interval
3. List is filterable by type
4. Missing source/explanation → 422
5. Updates maintain version history
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import FinancialAssumption, FinancialAssumptionType, FinancialAssumptionVersion
from src.simulation.assumption_service import (
    create_assumption,
    get_assumption_history,
    list_assumptions,
    update_assumption,
)

ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
EVIDENCE_ID = uuid.uuid4()


def _make_session() -> AsyncMock:
    session = AsyncMock()
    added: list = []

    def capture_add(obj: object) -> None:
        added.append(obj)

    session.add = capture_add
    session._added = added
    return session


class TestAssumptionCreation:
    """Scenario 1: Creation stores all required fields."""

    @pytest.mark.asyncio
    async def test_creates_with_all_fields(self) -> None:
        """All required fields are persisted on creation."""
        session = _make_session()
        data = {
            "assumption_type": FinancialAssumptionType.COST_PER_ROLE,
            "name": "Senior Analyst hourly rate",
            "value": 150.0,
            "unit": "USD/hour",
            "confidence": 0.8,
            "source_evidence_id": EVIDENCE_ID,
        }
        assumption = await create_assumption(session, ENGAGEMENT_ID, data)
        assert assumption.engagement_id == ENGAGEMENT_ID
        assert assumption.assumption_type == FinancialAssumptionType.COST_PER_ROLE
        assert assumption.name == "Senior Analyst hourly rate"
        assert assumption.value == 150.0
        assert assumption.unit == "USD/hour"
        assert assumption.confidence == 0.8
        assert assumption.source_evidence_id == EVIDENCE_ID

    @pytest.mark.asyncio
    async def test_creates_with_confidence_explanation(self) -> None:
        """Assumption with explanation instead of evidence reference."""
        session = _make_session()
        data = {
            "assumption_type": FinancialAssumptionType.VOLUME_FORECAST,
            "name": "Q3 transaction volume",
            "value": 50000,
            "unit": "transactions/quarter",
            "confidence": 0.6,
            "confidence_explanation": "Based on industry benchmarks",
        }
        assumption = await create_assumption(session, ENGAGEMENT_ID, data)
        assert assumption.confidence_explanation == "Based on industry benchmarks"
        assert assumption.source_evidence_id is None


class TestRangeBearingAssumption:
    """Scenario 2: Range-bearing assumption stores confidence interval."""

    @pytest.mark.asyncio
    async def test_stores_confidence_range(self) -> None:
        """Confidence range (±20%) is captured."""
        session = _make_session()
        data = {
            "assumption_type": FinancialAssumptionType.COST_PER_ROLE,
            "name": "Senior Analyst hourly rate",
            "value": 150.0,
            "unit": "USD/hour",
            "confidence": 0.8,
            "confidence_range": 0.20,
            "source_evidence_id": EVIDENCE_ID,
        }
        assumption = await create_assumption(session, ENGAGEMENT_ID, data)
        assert assumption.value == 150.0
        assert assumption.unit == "USD/hour"
        assert assumption.confidence == 0.8
        assert assumption.confidence_range == 0.20


class TestAssumptionFiltering:
    """Scenario 3: List is filterable by type with evidence links."""

    @pytest.mark.asyncio
    async def test_list_filters_by_type(self) -> None:
        """Only matching assumption_type returned when filter applied."""
        cost_assumption = MagicMock(spec=FinancialAssumption)
        cost_assumption.assumption_type = FinancialAssumptionType.COST_PER_ROLE
        cost_assumption.id = uuid.uuid4()

        session = AsyncMock()
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = AsyncMock()
            if call_count == 1:
                # Count query (func.count() → scalar_one())
                result.scalar_one = MagicMock(return_value=1)
            else:
                # Data query
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=[cost_assumption])
                result.scalars = MagicMock(return_value=mock_scalars)
            return result

        session.execute = mock_execute
        result = await list_assumptions(
            session, ENGAGEMENT_ID,
            assumption_type=FinancialAssumptionType.COST_PER_ROLE,
        )
        assert result["total"] == 1


class TestSourceValidation:
    """Scenario 4: Missing source evidence requires confidence explanation."""

    @pytest.mark.asyncio
    async def test_missing_source_and_explanation_raises(self) -> None:
        """No source_evidence_id AND no confidence_explanation → ValueError."""
        session = _make_session()
        data = {
            "assumption_type": FinancialAssumptionType.COST_PER_ROLE,
            "name": "Rate",
            "value": 100.0,
            "unit": "USD/hour",
            "confidence": 0.5,
        }
        with pytest.raises(ValueError, match="source_evidence_id or confidence_explanation is required"):
            await create_assumption(session, ENGAGEMENT_ID, data)

    @pytest.mark.asyncio
    async def test_explanation_alone_is_sufficient(self) -> None:
        """confidence_explanation without source_evidence_id is valid."""
        session = _make_session()
        data = {
            "assumption_type": FinancialAssumptionType.COST_PER_ROLE,
            "name": "Rate",
            "value": 100.0,
            "unit": "USD/hour",
            "confidence": 0.5,
            "confidence_explanation": "Estimated from market data",
        }
        assumption = await create_assumption(session, ENGAGEMENT_ID, data)
        assert assumption.confidence_explanation == "Estimated from market data"


class TestVersionHistory:
    """Scenario 5: Updates maintain version history for audit."""

    @pytest.mark.asyncio
    async def test_update_creates_version_entry(self) -> None:
        """Updating an assumption creates a version history entry with prior values."""
        existing = MagicMock(spec=FinancialAssumption)
        existing.id = uuid.uuid4()
        existing.value = 150.0
        existing.unit = "USD/hour"
        existing.confidence = 0.8
        existing.confidence_range = 0.20
        existing.source_evidence_id = EVIDENCE_ID
        existing.confidence_explanation = None
        existing.notes = None

        session = AsyncMock()
        result_mock = AsyncMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=existing)
        session.execute = AsyncMock(return_value=result_mock)

        added: list = []
        session.add = lambda obj: added.append(obj)

        await update_assumption(session, existing.id, {"value": 165.0}, USER_ID)

        # Version entry captures prior value
        assert len(added) == 1
        version = added[0]
        assert isinstance(version, FinancialAssumptionVersion)
        assert version.value == 150.0
        assert version.confidence == 0.8
        assert version.changed_by == USER_ID

        # Current assumption updated
        assert existing.value == 165.0

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self) -> None:
        """Updating non-existent assumption → ValueError."""
        session = AsyncMock()
        result_mock = AsyncMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ValueError, match="not found"):
            await update_assumption(session, uuid.uuid4(), {"value": 100.0}, USER_ID)

    @pytest.mark.asyncio
    async def test_history_retrieval(self) -> None:
        """Version history is retrievable for an assumption."""
        assumption_id = uuid.uuid4()
        v1 = MagicMock(spec=FinancialAssumptionVersion)
        v1.id = uuid.uuid4()
        v1.value = 150.0
        v1.changed_by = USER_ID

        session = AsyncMock()
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = AsyncMock()
            if call_count == 1:
                # Verify query — assumption exists
                result.scalar_one_or_none = MagicMock(return_value=assumption_id)
            else:
                # Versions query
                mock_scalars = MagicMock()
                mock_scalars.all = MagicMock(return_value=[v1])
                result.scalars = MagicMock(return_value=mock_scalars)
            return result

        session.execute = mock_execute

        versions = await get_assumption_history(session, assumption_id)
        assert len(versions) == 1
        assert versions[0].value == 150.0
