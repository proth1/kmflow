"""Tests for GdprComplianceService (src/core/services/gdpr_service.py)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.evidence import DataClassification
from src.core.models.gdpr import (
    LawfulBasis,
)
from src.core.services.gdpr_service import GdprComplianceService


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async DB session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar.return_value = 0
    session.execute = AsyncMock(return_value=mock_result)
    return session


@pytest.fixture
def service(mock_session: AsyncMock) -> GdprComplianceService:
    """Create a GdprComplianceService instance."""
    return GdprComplianceService(mock_session)


# ===========================================================================
# Classification access control
# ===========================================================================


class TestClassificationAccessControl:
    """GdprComplianceService.check_classification_access()."""

    def test_public_always_accessible(self, service: GdprComplianceService) -> None:
        assert service.check_classification_access(DataClassification.PUBLIC, has_restricted_access=False)
        assert service.check_classification_access(DataClassification.PUBLIC, has_restricted_access=True)

    def test_internal_accessible_without_restricted_access(self, service: GdprComplianceService) -> None:
        assert service.check_classification_access(DataClassification.INTERNAL, has_restricted_access=False)

    def test_confidential_accessible_without_restricted_access(self, service: GdprComplianceService) -> None:
        assert service.check_classification_access(DataClassification.CONFIDENTIAL, has_restricted_access=False)

    def test_restricted_requires_restricted_access(self, service: GdprComplianceService) -> None:
        assert not service.check_classification_access(DataClassification.RESTRICTED, has_restricted_access=False)
        assert service.check_classification_access(DataClassification.RESTRICTED, has_restricted_access=True)


# ===========================================================================
# DPA creation and listing
# ===========================================================================


class TestDpaService:
    """GdprComplianceService DPA operations."""

    @pytest.mark.asyncio
    async def test_create_dpa_adds_to_session(self, service: GdprComplianceService, mock_session: AsyncMock) -> None:
        """create_dpa adds a DPA object to the session."""
        engagement_id = uuid.uuid4()
        created_by = uuid.uuid4()

        await service.create_dpa(
            engagement_id=engagement_id,
            created_by=created_by,
            reference_number="DPA-001",
            controller_name="ACME Corp",
            processor_name="KMFlow Ltd",
            data_categories=["name", "email"],
            lawful_basis=LawfulBasis.LEGITIMATE_INTERESTS,
        )

        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_dpas_returns_empty_list(self, service: GdprComplianceService, mock_session: AsyncMock) -> None:
        """list_dpas returns an empty list when none exist."""
        engagement_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        dpas = await service.list_dpas(engagement_id)
        assert dpas == []

    @pytest.mark.asyncio
    async def test_get_dpa_returns_none_when_not_found(
        self, service: GdprComplianceService, mock_session: AsyncMock
    ) -> None:
        """get_dpa returns None when DPA doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_dpa(uuid.uuid4(), uuid.uuid4())
        assert result is None


# ===========================================================================
# Retention policy
# ===========================================================================


class TestRetentionPolicy:
    """GdprComplianceService retention policy operations."""

    @pytest.mark.asyncio
    async def test_get_retention_policy_returns_none_when_missing(
        self, service: GdprComplianceService, mock_session: AsyncMock
    ) -> None:
        """get_retention_policy returns None when no policy set for engagement."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_retention_policy(uuid.uuid4())
        assert result is None


# ===========================================================================
# Processing activities
# ===========================================================================


class TestProcessingActivities:
    """GdprComplianceService processing activity operations."""

    @pytest.mark.asyncio
    async def test_list_processing_activities_returns_empty(
        self, service: GdprComplianceService, mock_session: AsyncMock
    ) -> None:
        """list_processing_activities returns empty list when none exist."""
        engagement_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        activities = await service.list_processing_activities(engagement_id)
        assert activities == []
