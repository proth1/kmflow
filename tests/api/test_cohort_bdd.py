"""BDD tests for Story #391: Cohort Suppression and Anonymization.

Tests cohort size checking, export blocking, engagement-level
configuration, and default threshold behavior.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import Engagement
from src.security.cohort.suppression import CohortExportBlockedError, CohortSuppressionService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid.uuid4()


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _setup_engagement_cohort(session: AsyncMock, cohort_size: int | None) -> MagicMock:
    """Set up mock session to return an engagement with given cohort_minimum_size."""
    engagement = MagicMock(spec=Engagement)
    engagement.id = ENGAGEMENT_ID
    engagement.cohort_minimum_size = cohort_size

    # For _get_minimum: select(Engagement.id, Engagement.cohort_minimum_size)
    row_result = MagicMock()
    # one_or_none() returns a Row-like tuple (id, cohort_minimum_size)
    row_result.one_or_none.return_value = (ENGAGEMENT_ID, cohort_size)
    session.execute = AsyncMock(return_value=row_result)

    return engagement


# ---------------------------------------------------------------------------
# BDD Scenario 1: Analytics for group below minimum cohort size are suppressed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_below_minimum_suppressed() -> None:
    """Given a group of 3 and minimum=5,
    When analytics is queried,
    Then response has suppressed=true and reason=insufficient_cohort_size."""
    session = _mock_session()
    _setup_engagement_cohort(session, 5)

    service = CohortSuppressionService(session)
    result = await service.check_cohort(
        engagement_id=ENGAGEMENT_ID,
        cohort_size=3,
        context="analytics_query",
    )

    assert result["suppressed"] is True
    assert result["reason"] == "insufficient_cohort_size"
    assert result["cohort_size_observed"] == 3
    assert result["cohort_minimum"] == 5
    assert result["data"] is None


@pytest.mark.asyncio
async def test_scenario_1_at_boundary_suppressed() -> None:
    """A group of exactly 4 (below 5) is also suppressed."""
    session = _mock_session()
    _setup_engagement_cohort(session, 5)

    service = CohortSuppressionService(session)
    result = await service.check_cohort(
        engagement_id=ENGAGEMENT_ID,
        cohort_size=4,
    )

    assert result["suppressed"] is True
    assert result["cohort_size_observed"] == 4


# ---------------------------------------------------------------------------
# BDD Scenario 2: Analytics for group meeting minimum returned normally
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_2_at_minimum_not_suppressed() -> None:
    """Given a group of 5 and minimum=5,
    When analytics is queried,
    Then suppressed=false."""
    session = _mock_session()
    _setup_engagement_cohort(session, 5)

    service = CohortSuppressionService(session)
    result = await service.check_cohort(
        engagement_id=ENGAGEMENT_ID,
        cohort_size=5,
    )

    assert result["suppressed"] is False
    assert result["reason"] is None
    assert result["cohort_size_observed"] == 5
    assert result["cohort_minimum"] == 5


@pytest.mark.asyncio
async def test_scenario_2_above_minimum_not_suppressed() -> None:
    """Given a group of 10 and minimum=5,
    When analytics is queried,
    Then aggregated analytics returned normally."""
    session = _mock_session()
    _setup_engagement_cohort(session, 5)

    service = CohortSuppressionService(session)
    result = await service.check_cohort(
        engagement_id=ENGAGEMENT_ID,
        cohort_size=10,
    )

    assert result["suppressed"] is False
    assert result["cohort_size_observed"] == 10


# ---------------------------------------------------------------------------
# BDD Scenario 3: Configurable minimum takes immediate effect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_custom_minimum_applies() -> None:
    """Given engagement configured with minimum=10,
    Then groups of 8 are suppressed."""
    session = _mock_session()
    _setup_engagement_cohort(session, 10)

    service = CohortSuppressionService(session)
    result = await service.check_cohort(
        engagement_id=ENGAGEMENT_ID,
        cohort_size=8,
    )

    assert result["suppressed"] is True
    assert result["cohort_minimum"] == 10


@pytest.mark.asyncio
async def test_scenario_3_configure_engagement() -> None:
    """PATCH engagement settings updates the cohort minimum."""
    session = _mock_session()
    engagement = MagicMock(spec=Engagement)
    engagement.id = ENGAGEMENT_ID
    engagement.cohort_minimum_size = 5

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = engagement
    session.execute = AsyncMock(return_value=scalar_result)

    service = CohortSuppressionService(session)
    result = await service.configure_engagement(
        engagement_id=ENGAGEMENT_ID,
        minimum_cohort_size=10,
    )

    assert result["cohort_minimum_size"] == 10
    assert engagement.cohort_minimum_size == 10


@pytest.mark.asyncio
async def test_scenario_3_configure_rejects_below_2() -> None:
    """Minimum cohort size must be at least 2."""
    session = _mock_session()
    service = CohortSuppressionService(session)

    with pytest.raises(ValueError, match="at least 2"):
        await service.configure_engagement(
            engagement_id=ENGAGEMENT_ID,
            minimum_cohort_size=1,
        )


# ---------------------------------------------------------------------------
# BDD Scenario 4: Export of suppressed data is blocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_4_export_blocked_below_minimum() -> None:
    """Given a group of 3 below minimum=5,
    When export is requested,
    Then CohortExportBlockedError is raised."""
    session = _mock_session()
    _setup_engagement_cohort(session, 5)

    service = CohortSuppressionService(session)
    with pytest.raises(CohortExportBlockedError) as exc_info:
        await service.check_export(
            engagement_id=ENGAGEMENT_ID,
            cohort_size=3,
            requester="analyst@example.com",
        )

    assert exc_info.value.cohort_size == 3
    assert exc_info.value.minimum == 5
    assert "below minimum threshold" in str(exc_info.value)


@pytest.mark.asyncio
async def test_scenario_4_export_allowed_above_minimum() -> None:
    """Given a group of 10 above minimum=5,
    When export is requested,
    Then export is allowed."""
    session = _mock_session()
    _setup_engagement_cohort(session, 5)

    service = CohortSuppressionService(session)
    result = await service.check_export(
        engagement_id=ENGAGEMENT_ID,
        cohort_size=10,
        requester="analyst@example.com",
    )

    assert result["allowed"] is True
    assert result["cohort_size"] == 10


# ---------------------------------------------------------------------------
# Default threshold behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_threshold_when_not_configured() -> None:
    """When engagement has no cohort config (None), platform default of 5 applies."""
    session = _mock_session()
    _setup_engagement_cohort(session, None)

    service = CohortSuppressionService(session)
    result = await service.check_cohort(
        engagement_id=ENGAGEMENT_ID,
        cohort_size=4,
    )

    assert result["suppressed"] is True
    assert result["cohort_minimum"] == 5  # Platform default


@pytest.mark.asyncio
async def test_get_engagement_config_default() -> None:
    """Get config for engagement without override shows default."""
    session = _mock_session()
    _setup_engagement_cohort(session, None)

    service = CohortSuppressionService(session)
    result = await service.get_engagement_config(
        engagement_id=ENGAGEMENT_ID,
    )

    assert result["cohort_minimum_size"] == 5
    assert result["is_default"] is True


@pytest.mark.asyncio
async def test_get_engagement_config_custom() -> None:
    """Get config for engagement with override shows custom value."""
    session = _mock_session()
    _setup_engagement_cohort(session, 10)

    service = CohortSuppressionService(session)
    result = await service.get_engagement_config(
        engagement_id=ENGAGEMENT_ID,
    )

    assert result["cohort_minimum_size"] == 10
    assert result["is_default"] is False


# ---------------------------------------------------------------------------
# Unit: CohortExportBlockedError
# ---------------------------------------------------------------------------


def test_export_blocked_error_message() -> None:
    """Error message includes cohort size and minimum."""
    error = CohortExportBlockedError(cohort_size=3, minimum=5)
    assert "cohort size 3" in str(error)
    assert "minimum threshold 5" in str(error)
    assert error.cohort_size == 3
    assert error.minimum == 5


# ---------------------------------------------------------------------------
# Audit logging for blocked exports
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_blocked_creates_audit_log() -> None:
    """When an export is blocked, an AuditLog entry is created."""
    session = _mock_session()
    _setup_engagement_cohort(session, 5)

    service = CohortSuppressionService(session)
    with pytest.raises(CohortExportBlockedError):
        await service.check_export(
            engagement_id=ENGAGEMENT_ID,
            cohort_size=3,
            requester="analyst@example.com",
        )

    # Verify audit log was added to session
    session.add.assert_called_once()
    audit_entry = session.add.call_args[0][0]
    assert audit_entry.action.value == "export_blocked"
    assert audit_entry.engagement_id == ENGAGEMENT_ID
    assert audit_entry.actor == "analyst@example.com"


# ---------------------------------------------------------------------------
# Non-existent engagement handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nonexistent_engagement_raises_value_error() -> None:
    """When engagement does not exist, _get_minimum raises ValueError."""
    session = _mock_session()
    row_result = MagicMock()
    row_result.one_or_none.return_value = None
    session.execute = AsyncMock(return_value=row_result)

    service = CohortSuppressionService(session)
    with pytest.raises(ValueError, match="not found"):
        await service.check_cohort(
            engagement_id=uuid.uuid4(),
            cohort_size=3,
        )


@pytest.mark.asyncio
async def test_configure_commits_session() -> None:
    """configure_engagement commits the session after flushing."""
    session = _mock_session()
    engagement = MagicMock(spec=Engagement)
    engagement.id = ENGAGEMENT_ID
    engagement.cohort_minimum_size = 5

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = engagement
    session.execute = AsyncMock(return_value=scalar_result)

    service = CohortSuppressionService(session)
    await service.configure_engagement(
        engagement_id=ENGAGEMENT_ID,
        minimum_cohort_size=10,
    )

    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()
