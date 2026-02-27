"""BDD tests for LLM Audit Trail service (Story #386).

Covers 4 scenarios from the GitHub Issue:
  1. List LLM audit entries for an engagement
  2. Flag a hallucination on an audit entry
  3. Get suggestion disposition stats
  4. Immutable audit log fields
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.services.llm_audit import LLMAuditService
from src.core.models.llm_audit import LLMAuditLog
from src.core.models.simulation import SuggestionDisposition


def _make_audit_log(**overrides: Any) -> MagicMock:
    """Create a mock LLMAuditLog."""
    log = MagicMock(spec=LLMAuditLog)
    log.id = overrides.get("id", uuid.uuid4())
    log.scenario_id = overrides.get("scenario_id", uuid.uuid4())
    log.user_id = overrides.get("user_id")
    log.prompt_tokens = overrides.get("prompt_tokens", 100)
    log.completion_tokens = overrides.get("completion_tokens", 200)
    log.model_name = overrides.get("model_name", "gpt-4")
    log.evidence_ids = overrides.get("evidence_ids")
    log.error_message = overrides.get("error_message")
    log.hallucination_flagged = overrides.get("hallucination_flagged", False)
    log.hallucination_reason = overrides.get("hallucination_reason")
    log.flagged_at = overrides.get("flagged_at")
    log.flagged_by_user_id = overrides.get("flagged_by_user_id")
    log.created_at = overrides.get("created_at", datetime.now(UTC))
    return log


@pytest.fixture()
def mock_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture()
def service(mock_session: AsyncMock) -> LLMAuditService:
    return LLMAuditService(mock_session)


# ---------------------------------------------------------------------------
# Scenario 1: List LLM audit entries for an engagement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_by_engagement_returns_paginated(
    service: LLMAuditService, mock_session: AsyncMock
) -> None:
    """Given audit entries exist for an engagement,
    When I query with defaults,
    Then I get a paginated response with items."""
    engagement_id = uuid.uuid4()
    log1 = _make_audit_log()
    log2 = _make_audit_log()

    count_result = MagicMock()
    count_result.scalar.return_value = 2

    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = [log1, log2]

    mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

    result = await service.list_by_engagement(engagement_id=engagement_id)
    assert result["total"] == 2
    assert len(result["items"]) == 2
    assert result["limit"] == 20
    assert result["offset"] == 0


@pytest.mark.asyncio
async def test_list_by_engagement_with_date_filter(
    service: LLMAuditService, mock_session: AsyncMock
) -> None:
    """Given audit entries, When I filter by date range,
    Then only entries in range are returned."""
    engagement_id = uuid.uuid4()
    from_date = datetime(2026, 1, 1, tzinfo=UTC)
    to_date = datetime(2026, 1, 31, tzinfo=UTC)

    count_result = MagicMock()
    count_result.scalar.return_value = 1

    log = _make_audit_log()
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = [log]

    mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

    result = await service.list_by_engagement(
        engagement_id=engagement_id, from_date=from_date, to_date=to_date
    )
    assert result["total"] == 1
    assert len(result["items"]) == 1


@pytest.mark.asyncio
async def test_list_by_engagement_pagination(
    service: LLMAuditService, mock_session: AsyncMock
) -> None:
    """Given many entries, When I paginate, Then offset/limit are respected."""
    engagement_id = uuid.uuid4()

    count_result = MagicMock()
    count_result.scalar.return_value = 50

    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = [_make_audit_log() for _ in range(10)]

    mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

    result = await service.list_by_engagement(
        engagement_id=engagement_id, limit=10, offset=20
    )
    assert result["total"] == 50
    assert result["limit"] == 10
    assert result["offset"] == 20
    assert len(result["items"]) == 10


@pytest.mark.asyncio
async def test_list_by_engagement_empty(
    service: LLMAuditService, mock_session: AsyncMock
) -> None:
    """Given no entries, When I query, Then I get empty list with total=0."""
    count_result = MagicMock()
    count_result.scalar.return_value = 0

    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = []

    mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

    result = await service.list_by_engagement(engagement_id=uuid.uuid4())
    assert result["total"] == 0
    assert result["items"] == []


# ---------------------------------------------------------------------------
# Scenario 2: Flag a hallucination on an audit entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_hallucination_sets_fields(
    service: LLMAuditService, mock_session: AsyncMock
) -> None:
    """Given an audit entry exists, When I flag it as hallucination,
    Then hallucination fields are set."""
    log = _make_audit_log()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = log

    mock_session.execute = AsyncMock(return_value=result_mock)

    audit_log_id = log.id
    user_id = uuid.uuid4()
    await service.flag_hallucination(
        audit_log_id=audit_log_id, reason="Invented citation", flagged_by=user_id
    )

    assert log.hallucination_flagged is True
    assert log.hallucination_reason == "Invented citation"
    assert log.flagged_by_user_id == user_id
    assert log.flagged_at is not None
    mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_flag_hallucination_not_found(
    service: LLMAuditService, mock_session: AsyncMock
) -> None:
    """Given no audit entry, When I flag, Then ValueError is raised."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=result_mock)

    with pytest.raises(ValueError, match="not found"):
        await service.flag_hallucination(
            audit_log_id=uuid.uuid4(),
            reason="Fake reason",
            flagged_by=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_flag_hallucination_serializes_response(
    service: LLMAuditService, mock_session: AsyncMock
) -> None:
    """When flagged, the returned dict includes hallucination fields."""
    log = _make_audit_log(hallucination_flagged=False)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = log
    mock_session.execute = AsyncMock(return_value=result_mock)

    result = await service.flag_hallucination(
        audit_log_id=log.id, reason="Bad data", flagged_by=uuid.uuid4()
    )

    assert result["hallucination_flagged"] is True
    assert result["hallucination_reason"] == "Bad data"


# ---------------------------------------------------------------------------
# Scenario 3: Get suggestion disposition stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stats_computes_rates(
    service: LLMAuditService, mock_session: AsyncMock
) -> None:
    """Given suggestions with various dispositions,
    When I get stats, Then acceptance/modification/rejection rates are computed."""
    engagement_id = uuid.uuid4()

    # Mock: total audit entries
    count_result = MagicMock()
    count_result.scalar.return_value = 10

    # Mock: suggestion disposition counts
    sugg_result = MagicMock()
    sugg_result.__iter__ = MagicMock(
        return_value=iter([
            (SuggestionDisposition.ACCEPTED, 6),
            (SuggestionDisposition.MODIFIED, 2),
            (SuggestionDisposition.REJECTED, 2),
        ])
    )

    # Mock: hallucination count
    halluc_result = MagicMock()
    halluc_result.scalar.return_value = 1

    mock_session.execute = AsyncMock(
        side_effect=[count_result, sugg_result, halluc_result]
    )

    result = await service.get_stats(engagement_id=engagement_id)

    assert result["total_entries"] == 10
    assert result["total_suggestions"] == 10
    assert result["accepted_count"] == 6
    assert result["modified_count"] == 2
    assert result["rejected_count"] == 2
    assert result["hallucination_flagged_count"] == 1
    assert result["acceptance_rate"] == 60.0
    assert result["modification_rate"] == 20.0
    assert result["rejection_rate"] == 20.0


@pytest.mark.asyncio
async def test_get_stats_zero_suggestions(
    service: LLMAuditService, mock_session: AsyncMock
) -> None:
    """Given no suggestions, rates should be 0.0."""
    count_result = MagicMock()
    count_result.scalar.return_value = 0

    sugg_result = MagicMock()
    sugg_result.__iter__ = MagicMock(return_value=iter([]))

    halluc_result = MagicMock()
    halluc_result.scalar.return_value = 0

    mock_session.execute = AsyncMock(
        side_effect=[count_result, sugg_result, halluc_result]
    )

    result = await service.get_stats(engagement_id=uuid.uuid4())

    assert result["total_suggestions"] == 0
    assert result["acceptance_rate"] == 0.0
    assert result["modification_rate"] == 0.0
    assert result["rejection_rate"] == 0.0


@pytest.mark.asyncio
async def test_get_stats_with_date_range(
    service: LLMAuditService, mock_session: AsyncMock
) -> None:
    """Given date range, stats are filtered accordingly."""
    count_result = MagicMock()
    count_result.scalar.return_value = 5

    sugg_result = MagicMock()
    sugg_result.__iter__ = MagicMock(
        return_value=iter([(SuggestionDisposition.ACCEPTED, 3)])
    )

    halluc_result = MagicMock()
    halluc_result.scalar.return_value = 0

    mock_session.execute = AsyncMock(
        side_effect=[count_result, sugg_result, halluc_result]
    )

    result = await service.get_stats(
        engagement_id=uuid.uuid4(),
        from_date=datetime(2026, 1, 1, tzinfo=UTC),
        to_date=datetime(2026, 1, 31, tzinfo=UTC),
    )

    assert result["total_entries"] == 5
    assert result["accepted_count"] == 3
    assert result["acceptance_rate"] == 100.0


# ---------------------------------------------------------------------------
# Scenario 4: Immutable audit log fields
# ---------------------------------------------------------------------------


def test_immutable_fields_defined() -> None:
    """The service defines which fields are immutable."""
    assert "prompt_text" in LLMAuditService.IMMUTABLE_FIELDS
    assert "response_text" in LLMAuditService.IMMUTABLE_FIELDS
    assert "evidence_ids" in LLMAuditService.IMMUTABLE_FIELDS
    assert "model_name" in LLMAuditService.IMMUTABLE_FIELDS
    assert "created_at" in LLMAuditService.IMMUTABLE_FIELDS


def test_immutable_fields_is_frozenset() -> None:
    """Immutable fields set cannot be modified."""
    assert isinstance(LLMAuditService.IMMUTABLE_FIELDS, frozenset)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_serialize_audit_log() -> None:
    """Serialization converts UUIDs to strings and datetimes to ISO format."""
    log_id = uuid.uuid4()
    scenario_id = uuid.uuid4()
    user_id = uuid.uuid4()
    created = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)

    log = _make_audit_log(
        id=log_id,
        scenario_id=scenario_id,
        user_id=user_id,
        prompt_tokens=50,
        completion_tokens=150,
        model_name="claude-3-opus",
        evidence_ids=["ev1", "ev2"],
        hallucination_flagged=False,
        created_at=created,
    )

    result = LLMAuditService._serialize(log)

    assert result["id"] == str(log_id)
    assert result["scenario_id"] == str(scenario_id)
    assert result["user_id"] == str(user_id)
    assert result["prompt_tokens"] == 50
    assert result["completion_tokens"] == 150
    assert result["model_name"] == "claude-3-opus"
    assert result["evidence_ids"] == ["ev1", "ev2"]
    assert result["hallucination_flagged"] is False
    assert result["created_at"] == "2026-01-15T12:00:00+00:00"


def test_serialize_null_user_id() -> None:
    """Serialization handles None user_id."""
    log = _make_audit_log(user_id=None)
    result = LLMAuditService._serialize(log)
    assert result["user_id"] is None
