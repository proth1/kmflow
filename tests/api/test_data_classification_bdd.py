"""BDD tests for Data Classification and GDPR Compliance (Story #317).

Tests evidence classification access control, retention policy enforcement,
processing activity (ROPA) tracking, and compliance reporting.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.evidence import DataClassification, EvidenceItem, ValidationStatus
from src.core.models.gdpr import (
    DataProcessingActivity,
    LawfulBasis,
    RetentionAction,
    RetentionPolicy,
)
from src.core.services.gdpr_service import GdprComplianceService

ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class TestClassificationAccessControl:
    """Scenario 2: Restricted evidence is inaccessible to unauthorized users."""

    def test_public_accessible_without_restricted_grant(self) -> None:
        service = GdprComplianceService(AsyncMock())
        assert service.check_classification_access(
            DataClassification.PUBLIC, has_restricted_access=False
        ) is True

    def test_internal_accessible_without_restricted_grant(self) -> None:
        service = GdprComplianceService(AsyncMock())
        assert service.check_classification_access(
            DataClassification.INTERNAL, has_restricted_access=False
        ) is True

    def test_confidential_accessible_without_restricted_grant(self) -> None:
        service = GdprComplianceService(AsyncMock())
        assert service.check_classification_access(
            DataClassification.CONFIDENTIAL, has_restricted_access=False
        ) is True

    def test_restricted_denied_without_explicit_grant(self) -> None:
        """Given a user without Restricted access,
        When accessing Restricted evidence,
        Then access is denied."""
        service = GdprComplianceService(AsyncMock())
        assert service.check_classification_access(
            DataClassification.RESTRICTED, has_restricted_access=False
        ) is False

    def test_restricted_allowed_with_explicit_grant(self) -> None:
        service = GdprComplianceService(AsyncMock())
        assert service.check_classification_access(
            DataClassification.RESTRICTED, has_restricted_access=True
        ) is True


class TestRetentionPolicyEnforcement:
    """Scenario 4: Evidence older than retention period is archived."""

    @pytest.mark.asyncio
    async def test_create_retention_policy(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        # No existing policy
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result)

        service = GdprComplianceService(mock_session)
        await service.set_retention_policy(
            engagement_id=ENGAGEMENT_ID,
            retention_days=90,
            action=RetentionAction.ARCHIVE,
        )

        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert isinstance(added, RetentionPolicy)
        assert added.retention_days == 90
        assert added.action == RetentionAction.ARCHIVE

    @pytest.mark.asyncio
    async def test_enforce_retention_archives_expired_items(self) -> None:
        """Given 90-day retention, When enforcement runs,
        Then old items are archived, current items untouched."""
        mock_session = AsyncMock()

        # Mock policy lookup
        policy = MagicMock(spec=RetentionPolicy)
        policy.engagement_id = ENGAGEMENT_ID
        policy.retention_days = 90
        policy.action = RetentionAction.ARCHIVE

        policy_result = MagicMock()
        policy_result.scalar_one_or_none.return_value = policy

        # Mock expired items query
        old_item = MagicMock(spec=EvidenceItem)
        old_item.id = uuid.uuid4()
        old_item.validation_status = ValidationStatus.ACTIVE

        items_result = MagicMock()
        items_scalars = MagicMock()
        items_scalars.all.return_value = [old_item]
        items_result.scalars.return_value = items_scalars

        mock_session.execute = AsyncMock(side_effect=[policy_result, items_result])

        service = GdprComplianceService(mock_session)
        result = await service.enforce_retention(ENGAGEMENT_ID)

        assert result["affected_count"] == 1
        assert result["action"] == "archive"
        assert old_item.validation_status == ValidationStatus.ARCHIVED

    @pytest.mark.asyncio
    async def test_enforce_retention_no_policy(self) -> None:
        """When no retention policy configured, return 0 affected."""
        mock_session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result)

        service = GdprComplianceService(mock_session)
        result = await service.enforce_retention(ENGAGEMENT_ID)
        assert result["affected_count"] == 0


class TestProcessingActivities:
    """Scenario 5: Processing activity linked to GDPR lawful basis."""

    @pytest.mark.asyncio
    async def test_create_processing_activity(self) -> None:
        """Given a processing activity record,
        Then it has a lawful_basis and article_6_basis."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        service = GdprComplianceService(mock_session)
        await service.create_processing_activity(
            engagement_id=ENGAGEMENT_ID,
            name="Evidence ingestion",
            lawful_basis=LawfulBasis.LEGITIMATE_INTERESTS,
            article_6_basis="Art. 6(1)(f)",
            created_by=USER_ID,
        )

        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert isinstance(added, DataProcessingActivity)
        assert added.name == "Evidence ingestion"
        assert added.lawful_basis == LawfulBasis.LEGITIMATE_INTERESTS
        assert added.article_6_basis == "Art. 6(1)(f)"

    @pytest.mark.asyncio
    async def test_create_consent_basis_activity(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        service = GdprComplianceService(mock_session)
        await service.create_processing_activity(
            engagement_id=ENGAGEMENT_ID,
            name="Desktop capture",
            lawful_basis=LawfulBasis.CONSENT,
            article_6_basis="Art. 6(1)(a)",
            created_by=USER_ID,
            description="Desktop task mining with explicit opt-in",
        )

        added = mock_session.add.call_args[0][0]
        assert added.lawful_basis == LawfulBasis.CONSENT
        assert added.description == "Desktop task mining with explicit opt-in"

    @pytest.mark.asyncio
    async def test_query_processing_activities(self) -> None:
        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        activity1 = MagicMock(spec=DataProcessingActivity)
        activity1.id = uuid.uuid4()
        activity1.engagement_id = ENGAGEMENT_ID
        activity1.name = "Evidence ingestion"
        activity1.description = None
        activity1.lawful_basis = LawfulBasis.LEGITIMATE_INTERESTS
        activity1.article_6_basis = "Art. 6(1)(f)"
        activity1.created_at = datetime(2026, 2, 27, tzinfo=UTC)
        activity1.created_by = USER_ID

        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = [activity1]
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        service = GdprComplianceService(mock_session)
        result = await service.query_processing_activities(ENGAGEMENT_ID)

        assert result["total"] == 2
        assert len(result["items"]) == 1
        assert result["items"][0]["lawful_basis"] == "legitimate_interests"


class TestComplianceReport:
    """Compliance report shows activities by lawful basis."""

    @pytest.mark.asyncio
    async def test_compliance_report_with_activities(self) -> None:
        mock_session = AsyncMock()

        # Basis counts
        basis_row = MagicMock()
        basis_row.lawful_basis = LawfulBasis.LEGITIMATE_INTERESTS
        basis_row.count = 3
        basis_result = MagicMock()
        basis_result.__iter__ = MagicMock(return_value=iter([basis_row]))

        # Classification counts
        class_row = MagicMock()
        class_row.classification = DataClassification.INTERNAL
        class_row.count = 10
        class_result = MagicMock()
        class_result.__iter__ = MagicMock(return_value=iter([class_row]))

        # Total activities
        total_result = MagicMock()
        total_result.scalar.return_value = 3

        mock_session.execute = AsyncMock(
            side_effect=[basis_result, class_result, total_result]
        )

        service = GdprComplianceService(mock_session)
        report = await service.get_compliance_report(ENGAGEMENT_ID)

        assert report["total_processing_activities"] == 3
        assert report["activities_by_lawful_basis"]["legitimate_interests"] == 3
        assert report["evidence_by_classification"]["internal"] == 10
        assert report["compliant"] is True

    @pytest.mark.asyncio
    async def test_compliance_report_no_activities_not_compliant(self) -> None:
        mock_session = AsyncMock()

        basis_result = MagicMock()
        basis_result.__iter__ = MagicMock(return_value=iter([]))

        class_result = MagicMock()
        class_result.__iter__ = MagicMock(return_value=iter([]))

        total_result = MagicMock()
        total_result.scalar.return_value = 0

        mock_session.execute = AsyncMock(
            side_effect=[basis_result, class_result, total_result]
        )

        service = GdprComplianceService(mock_session)
        report = await service.get_compliance_report(ENGAGEMENT_ID)

        assert report["total_processing_activities"] == 0
        assert report["compliant"] is False


class TestLawfulBasisEnum:
    """All six GDPR Article 6 lawful bases are represented."""

    def test_consent(self) -> None:
        assert LawfulBasis.CONSENT == "consent"

    def test_contract(self) -> None:
        assert LawfulBasis.CONTRACT == "contract"

    def test_legal_obligation(self) -> None:
        assert LawfulBasis.LEGAL_OBLIGATION == "legal_obligation"

    def test_vital_interests(self) -> None:
        assert LawfulBasis.VITAL_INTERESTS == "vital_interests"

    def test_public_task(self) -> None:
        assert LawfulBasis.PUBLIC_TASK == "public_task"

    def test_legitimate_interests(self) -> None:
        assert LawfulBasis.LEGITIMATE_INTERESTS == "legitimate_interests"


class TestDataClassificationEnum:
    """All four sensitivity levels are represented."""

    def test_public(self) -> None:
        assert DataClassification.PUBLIC == "public"

    def test_internal(self) -> None:
        assert DataClassification.INTERNAL == "internal"

    def test_confidential(self) -> None:
        assert DataClassification.CONFIDENTIAL == "confidential"

    def test_restricted(self) -> None:
        assert DataClassification.RESTRICTED == "restricted"
