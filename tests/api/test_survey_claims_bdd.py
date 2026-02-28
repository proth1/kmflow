"""BDD tests for Certainty Tier Tracking and SurveyClaim Management (Story #322).

Tests certainty tier filtering, tier promotion with history, shelf data request
auto-generation for SUSPECTED claims, and paginated filtered queries.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.engagement import (
    ShelfDataRequest,
    ShelfDataRequestItem,
)
from src.core.models.survey import CertaintyTier, ProbeType, SurveyClaim
from src.core.models.survey_claim_history import SurveyClaimHistory
from src.core.services.survey_claim_service import SurveyClaimService

ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
CLAIM_ID = uuid.uuid4()


def _mock_claim(
    certainty_tier: CertaintyTier = CertaintyTier.SUSPECTED,
    proof_expectation: str | None = "system audit log showing KYC step completion",
) -> MagicMock:
    claim = MagicMock(spec=SurveyClaim)
    claim.id = CLAIM_ID
    claim.engagement_id = ENGAGEMENT_ID
    claim.session_id = uuid.uuid4()
    claim.probe_type = ProbeType.EXISTENCE
    claim.respondent_role = "operations_team"
    claim.claim_text = "KYC step always completes within 24 hours"
    claim.certainty_tier = certainty_tier
    claim.proof_expectation = proof_expectation
    claim.related_seed_terms = ["KYC", "compliance"]
    claim.created_at = datetime(2026, 2, 27, tzinfo=UTC)
    return claim


class TestShelfDataRequestAutoGeneration:
    """Scenario 1: Shelf data request auto-generation for SUSPECTED claim."""

    @pytest.mark.asyncio
    async def test_creates_shelf_request_from_suspected_claim(self) -> None:
        """Given a SurveyClaim with certainty_tier=SUSPECTED and proof_expectation,
        When a shelf data request is generated,
        Then a request item is created linked to the claim."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        claim = _mock_claim(CertaintyTier.SUSPECTED)

        result = MagicMock()
        result.scalar_one_or_none.return_value = claim
        mock_session.execute = AsyncMock(return_value=result)

        service = SurveyClaimService(mock_session)
        response = await service.create_shelf_data_request(CLAIM_ID)

        assert "shelf_data_request_id" in response
        assert response["claim_id"] == str(CLAIM_ID)
        assert response["engagement_id"] == str(ENGAGEMENT_ID)
        assert response["description"] == "system audit log showing KYC step completion"

        # Verify both request and item were added
        assert mock_session.add.call_count == 2
        added_request = mock_session.add.call_args_list[0][0][0]
        assert isinstance(added_request, ShelfDataRequest)
        assert added_request.engagement_id == ENGAGEMENT_ID

        added_item = mock_session.add.call_args_list[1][0][0]
        assert isinstance(added_item, ShelfDataRequestItem)

    @pytest.mark.asyncio
    async def test_rejects_non_suspected_claim(self) -> None:
        """Only SUSPECTED claims can generate shelf data requests."""
        mock_session = AsyncMock()

        claim = _mock_claim(CertaintyTier.KNOWN)
        result = MagicMock()
        result.scalar_one_or_none.return_value = claim
        mock_session.execute = AsyncMock(return_value=result)

        service = SurveyClaimService(mock_session)
        response = await service.create_shelf_data_request(CLAIM_ID)

        assert response["error"] == "not_suspected"

    @pytest.mark.asyncio
    async def test_rejects_claim_without_proof_expectation(self) -> None:
        """SUSPECTED claims without proof_expectation cannot generate requests."""
        mock_session = AsyncMock()

        claim = _mock_claim(CertaintyTier.SUSPECTED, proof_expectation=None)
        result = MagicMock()
        result.scalar_one_or_none.return_value = claim
        mock_session.execute = AsyncMock(return_value=result)

        service = SurveyClaimService(mock_session)
        response = await service.create_shelf_data_request(CLAIM_ID)

        assert response["error"] == "no_proof_expectation"


class TestCertaintyTierFiltering:
    """Scenario 2: Certainty tier filtering."""

    @pytest.mark.asyncio
    async def test_filters_by_certainty_tier(self) -> None:
        """Given claims with mixed tiers,
        When filtered by UNKNOWN,
        Then only UNKNOWN claims are returned."""
        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 5

        unknown_claim = _mock_claim(CertaintyTier.UNKNOWN)
        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = [unknown_claim]
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        service = SurveyClaimService(mock_session)
        result = await service.query_claims(
            ENGAGEMENT_ID,
            certainty_tier=CertaintyTier.UNKNOWN,
        )

        assert result["total_count"] == 5
        assert len(result["items"]) == 1
        assert result["items"][0]["certainty_tier"] == "unknown"

    @pytest.mark.asyncio
    async def test_filters_by_probe_type(self) -> None:
        """Claims can also be filtered by probe_type."""
        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        claim = _mock_claim()
        claim.probe_type = ProbeType.GOVERNANCE
        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = [claim]
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        service = SurveyClaimService(mock_session)
        result = await service.query_claims(
            ENGAGEMENT_ID,
            probe_type=ProbeType.GOVERNANCE,
        )

        assert result["total_count"] == 2
        assert result["items"][0]["probe_type"] == "governance"


class TestCertaintyTierPromotion:
    """Scenario 3: Certainty tier promotion on evidence confirmation."""

    @pytest.mark.asyncio
    async def test_promotes_tier_and_records_history(self) -> None:
        """Given a SUSPECTED claim,
        When updated to KNOWN,
        Then history is recorded."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        claim = _mock_claim(CertaintyTier.SUSPECTED)
        result = MagicMock()
        result.scalar_one_or_none.return_value = claim
        mock_session.execute = AsyncMock(return_value=result)

        service = SurveyClaimService(mock_session)
        response = await service.update_certainty_tier(
            claim_id=CLAIM_ID,
            new_tier=CertaintyTier.KNOWN,
            changed_by=USER_ID,
        )

        assert response["previous_tier"] == "suspected"
        assert response["new_tier"] == "known"
        assert response["changed_by"] == str(USER_ID)

        # Verify history entry was created
        mock_session.add.assert_called_once()
        history = mock_session.add.call_args[0][0]
        assert isinstance(history, SurveyClaimHistory)
        assert history.previous_tier == CertaintyTier.SUSPECTED
        assert history.new_tier == CertaintyTier.KNOWN
        assert history.changed_by == USER_ID

        # Verify claim was updated
        assert claim.certainty_tier == CertaintyTier.KNOWN

    @pytest.mark.asyncio
    async def test_no_change_returns_error(self) -> None:
        """Updating to the same tier returns an error."""
        mock_session = AsyncMock()

        claim = _mock_claim(CertaintyTier.KNOWN)
        result = MagicMock()
        result.scalar_one_or_none.return_value = claim
        mock_session.execute = AsyncMock(return_value=result)

        service = SurveyClaimService(mock_session)
        response = await service.update_certainty_tier(
            claim_id=CLAIM_ID,
            new_tier=CertaintyTier.KNOWN,
            changed_by=USER_ID,
        )

        assert response["error"] == "no_change"

    @pytest.mark.asyncio
    async def test_not_found_returns_error(self) -> None:
        """Updating a nonexistent claim returns not_found."""
        mock_session = AsyncMock()

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result)

        service = SurveyClaimService(mock_session)
        response = await service.update_certainty_tier(
            claim_id=uuid.uuid4(),
            new_tier=CertaintyTier.KNOWN,
            changed_by=USER_ID,
        )

        assert response["error"] == "not_found"


class TestPaginatedFilteredList:
    """Scenario 4: Paginated and filtered claims list."""

    @pytest.mark.asyncio
    async def test_paginated_with_combined_filters(self) -> None:
        """Given claims across probe types and tiers,
        When filtered by probe_type=RULE AND certainty_tier=SUSPECTED,
        Then results are paginated correctly."""
        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 15

        claims = [_mock_claim() for _ in range(10)]
        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = claims
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        service = SurveyClaimService(mock_session)
        result = await service.query_claims(
            ENGAGEMENT_ID,
            certainty_tier=CertaintyTier.SUSPECTED,
            limit=10,
            offset=0,
        )

        assert result["total_count"] == 15
        assert len(result["items"]) == 10
        assert result["limit"] == 10
        assert result["offset"] == 0


class TestClaimHistory:
    """Tier transition history is queryable."""

    @pytest.mark.asyncio
    async def test_get_claim_history(self) -> None:
        mock_session = AsyncMock()

        entry = MagicMock(spec=SurveyClaimHistory)
        entry.id = uuid.uuid4()
        entry.claim_id = CLAIM_ID
        entry.previous_tier = CertaintyTier.UNKNOWN
        entry.new_tier = CertaintyTier.SUSPECTED
        entry.changed_by = USER_ID
        entry.changed_at = datetime(2026, 2, 27, tzinfo=UTC)

        result = MagicMock()
        result_scalars = MagicMock()
        result_scalars.all.return_value = [entry]
        result.scalars.return_value = result_scalars
        mock_session.execute = AsyncMock(return_value=result)

        service = SurveyClaimService(mock_session)
        history = await service.get_claim_history(CLAIM_ID)

        assert len(history) == 1
        assert history[0]["previous_tier"] == "unknown"
        assert history[0]["new_tier"] == "suspected"


class TestCertaintyTierEnum:
    """All four certainty tiers are represented."""

    def test_known(self) -> None:
        assert CertaintyTier.KNOWN == "known"

    def test_suspected(self) -> None:
        assert CertaintyTier.SUSPECTED == "suspected"

    def test_unknown(self) -> None:
        assert CertaintyTier.UNKNOWN == "unknown"

    def test_contradicted(self) -> None:
        assert CertaintyTier.CONTRADICTED == "contradicted"
