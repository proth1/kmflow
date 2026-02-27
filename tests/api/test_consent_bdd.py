"""BDD tests for Consent Architecture (Story #382).

Tests consent recording, withdrawal, validation, and scope updates
for desktop endpoint capture per GDPR Art. 6(1)(a).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.security.consent.models import (
    ConsentStatus,
    EndpointConsentRecord,
    EndpointConsentType,
)
from src.security.consent.service import RETENTION_YEARS, ConsentService

PARTICIPANT_ID = uuid.uuid4()
ENGAGEMENT_ID = uuid.uuid4()
POLICY_BUNDLE_ID = uuid.uuid4()
RECORDER_ID = uuid.uuid4()


def _mock_consent_record(
    consent_type: EndpointConsentType = EndpointConsentType.OPT_IN,
    status: ConsentStatus = ConsentStatus.ACTIVE,
    scope: str = "application-usage-monitoring",
) -> EndpointConsentRecord:
    record = MagicMock(spec=EndpointConsentRecord)
    record.id = uuid.uuid4()
    record.participant_id = PARTICIPANT_ID
    record.engagement_id = ENGAGEMENT_ID
    record.consent_type = consent_type
    record.scope = scope
    record.policy_bundle_id = POLICY_BUNDLE_ID
    record.status = status
    record.recorded_by = RECORDER_ID
    record.recorded_at = datetime(2026, 2, 27, tzinfo=UTC)
    record.withdrawn_at = None
    record.retention_expires_at = datetime(2033, 2, 27, tzinfo=UTC)
    return record


class TestConsentRecording:
    """Scenario 1: Consent is recorded with all required fields."""

    @pytest.mark.asyncio
    async def test_record_opt_in_consent(self) -> None:
        """Given a participant, When consent is recorded,
        Then the record stores all required fields."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        service = ConsentService(mock_session)
        await service.record_consent(
            participant_id=PARTICIPANT_ID,
            engagement_id=ENGAGEMENT_ID,
            consent_type=EndpointConsentType.OPT_IN,
            scope="application-usage-monitoring",
            policy_bundle_id=POLICY_BUNDLE_ID,
            recorded_by=RECORDER_ID,
        )

        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert isinstance(added, EndpointConsentRecord)
        assert added.participant_id == PARTICIPANT_ID
        assert added.engagement_id == ENGAGEMENT_ID
        assert added.consent_type == EndpointConsentType.OPT_IN
        assert added.status == ConsentStatus.ACTIVE
        assert added.policy_bundle_id == POLICY_BUNDLE_ID
        assert added.recorded_by == RECORDER_ID
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_org_authorized_consent(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        service = ConsentService(mock_session)
        await service.record_consent(
            participant_id=PARTICIPANT_ID,
            engagement_id=ENGAGEMENT_ID,
            consent_type=EndpointConsentType.ORG_AUTHORIZED,
            scope="screen-content-capture",
            policy_bundle_id=POLICY_BUNDLE_ID,
            recorded_by=RECORDER_ID,
        )

        added = mock_session.add.call_args[0][0]
        assert added.consent_type == EndpointConsentType.ORG_AUTHORIZED
        assert added.scope == "screen-content-capture"

    @pytest.mark.asyncio
    async def test_record_hybrid_consent(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        service = ConsentService(mock_session)
        await service.record_consent(
            participant_id=PARTICIPANT_ID,
            engagement_id=ENGAGEMENT_ID,
            consent_type=EndpointConsentType.HYBRID,
            scope="application-usage-monitoring",
            policy_bundle_id=POLICY_BUNDLE_ID,
            recorded_by=RECORDER_ID,
        )

        added = mock_session.add.call_args[0][0]
        assert added.consent_type == EndpointConsentType.HYBRID

    @pytest.mark.asyncio
    async def test_retention_floor_set_to_7_years(self) -> None:
        """Consent records must have 7-year retention floor."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        service = ConsentService(mock_session)
        await service.record_consent(
            participant_id=PARTICIPANT_ID,
            engagement_id=ENGAGEMENT_ID,
            consent_type=EndpointConsentType.OPT_IN,
            scope="application-usage-monitoring",
            policy_bundle_id=POLICY_BUNDLE_ID,
            recorded_by=RECORDER_ID,
        )

        added = mock_session.add.call_args[0][0]
        assert added.retention_expires_at is not None
        # Should be approximately 7 years from now
        delta = added.retention_expires_at - datetime.now(UTC)
        assert delta.days >= (RETENTION_YEARS * 365 - 2)  # Allow 2-day margin


class TestConsentWithdrawal:
    """Scenario 2: Consent withdrawal marks participant data for deletion."""

    @pytest.mark.asyncio
    async def test_withdraw_active_consent(self) -> None:
        """Given active OPT_IN consent, When withdrawn,
        Then status is WITHDRAWN, deletion task queued."""
        mock_session = AsyncMock()
        record = _mock_consent_record()
        mock_session.get = AsyncMock(return_value=record)

        service = ConsentService(mock_session)
        result = await service.withdraw_consent(record.id)

        assert result is not None
        assert result["consent_id"] == str(record.id)
        assert result["deletion_task_id"] is not None
        assert result["deletion_targets"] == ["postgresql", "neo4j", "pgvector", "redis"]
        assert record.status == ConsentStatus.WITHDRAWN
        assert record.withdrawn_at is not None

    @pytest.mark.asyncio
    async def test_withdraw_nonexistent_returns_none(self) -> None:
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)

        service = ConsentService(mock_session)
        result = await service.withdraw_consent(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_withdraw_already_withdrawn_returns_none(self) -> None:
        mock_session = AsyncMock()
        record = _mock_consent_record(status=ConsentStatus.WITHDRAWN)
        mock_session.get = AsyncMock(return_value=record)

        service = ConsentService(mock_session)
        result = await service.withdraw_consent(record.id)
        assert result is None


class TestConsentValidation:
    """Scenario 4: Data processing blocked without valid consent."""

    @pytest.mark.asyncio
    async def test_participant_with_active_consent_passes(self) -> None:
        """Given P2 has active consent, validate_consent returns True."""
        mock_session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        mock_session.execute = AsyncMock(return_value=count_result)

        service = ConsentService(mock_session)
        result = await service.validate_consent(PARTICIPANT_ID, ENGAGEMENT_ID)
        assert result is True

    @pytest.mark.asyncio
    async def test_participant_without_consent_blocked(self) -> None:
        """Given P1 has no active consent, validate_consent returns False."""
        mock_session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_session.execute = AsyncMock(return_value=count_result)

        service = ConsentService(mock_session)
        result = await service.validate_consent(PARTICIPANT_ID, ENGAGEMENT_ID)
        assert result is False


class TestOrgScopeUpdate:
    """Scenario 3: Scope change on org-authorized consent triggers notification."""

    @pytest.mark.asyncio
    async def test_scope_expansion_identifies_affected_participants(self) -> None:
        """Given ORG_AUTHORIZED consent, When scope expanded,
        Then affected participants identified and notification emitted."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        record1 = _mock_consent_record(
            consent_type=EndpointConsentType.ORG_AUTHORIZED,
            scope="application-usage-monitoring",
        )
        record1.participant_id = uuid.uuid4()

        record2 = _mock_consent_record(
            consent_type=EndpointConsentType.ORG_AUTHORIZED,
            scope="application-usage-monitoring",
        )
        record2.participant_id = uuid.uuid4()

        select_result = MagicMock()
        select_scalars = MagicMock()
        select_scalars.all.return_value = [record1, record2]
        select_result.scalars.return_value = select_scalars
        mock_session.execute = AsyncMock(return_value=select_result)

        service = ConsentService(mock_session)
        result = await service.update_org_scope(
            ENGAGEMENT_ID, "screen-content-capture", updated_by=RECORDER_ID,
        )

        assert result["new_scope"] == "screen-content-capture"
        assert len(result["affected_participant_ids"]) == 2
        assert result["notification_required"] is True
        # Verify old records withdrawn
        assert record1.status == ConsentStatus.WITHDRAWN
        assert record2.status == ConsentStatus.WITHDRAWN
        # Verify new records created via session.add
        assert mock_session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_scope_update_no_matching_records(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        select_result = MagicMock()
        select_scalars = MagicMock()
        select_scalars.all.return_value = []
        select_result.scalars.return_value = select_scalars
        mock_session.execute = AsyncMock(return_value=select_result)

        service = ConsentService(mock_session)
        result = await service.update_org_scope(ENGAGEMENT_ID, "new-scope", updated_by=RECORDER_ID)

        assert result["affected_participant_ids"] == []
        assert result["notification_required"] is False


class TestConsentQuery:
    """Test consent query with filters and pagination."""

    @pytest.mark.asyncio
    async def test_query_with_participant_filter(self) -> None:
        mock_session = AsyncMock()
        record = _mock_consent_record()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = [record]
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        service = ConsentService(mock_session)
        result = await service.query_consent(participant_id=PARTICIPANT_ID)

        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["participant_id"] == str(PARTICIPANT_ID)
        assert result["items"][0]["consent_type"] == "opt_in"

    @pytest.mark.asyncio
    async def test_query_empty_results(self) -> None:
        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = []
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        service = ConsentService(mock_session)
        result = await service.query_consent(engagement_id=ENGAGEMENT_ID)

        assert result["total"] == 0
        assert result["items"] == []


class TestConsentTypes:
    """Test all three consent type enums."""

    def test_opt_in_value(self) -> None:
        assert EndpointConsentType.OPT_IN == "opt_in"

    def test_org_authorized_value(self) -> None:
        assert EndpointConsentType.ORG_AUTHORIZED == "org_authorized"

    def test_hybrid_value(self) -> None:
        assert EndpointConsentType.HYBRID == "hybrid"
