"""BDD tests for POV Orchestrator API endpoints (Story #318).

Tests the progress tracking and version history endpoints added to
complete the orchestrator wiring for the 8-step LCD algorithm.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.routes.pov import (
    ProgressResponse,
    VersionHistoryResponse,
    _get_elements_for_model,
    get_job_progress,
    get_version_history,
)
from src.core.models import UserRole

# -- Fixtures ----------------------------------------------------------------


def _make_mock_user(role: UserRole = UserRole.ENGAGEMENT_LEAD) -> MagicMock:
    """Create a mock user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


def _make_mock_request(
    job_data: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock Request with a Redis client."""
    request = MagicMock()
    redis = AsyncMock()

    if job_data is not None:
        redis.get = AsyncMock(return_value=json.dumps(job_data))
    else:
        redis.get = AsyncMock(return_value=None)

    request.app.state.redis_client = redis
    return request


def _make_mock_model(
    engagement_id: uuid.UUID | None = None,
    version: int = 1,
    status: str = "COMPLETED",
    confidence_score: float = 0.75,
    element_count: int = 5,
) -> MagicMock:
    """Create a mock ProcessModel."""
    model = MagicMock()
    model.id = uuid.uuid4()
    model.engagement_id = engagement_id or uuid.uuid4()
    model.version = version
    model.status = status
    model.confidence_score = confidence_score
    model.element_count = element_count
    model.generated_at = None
    return model


# ============================================================
# Scenario 2: Progress tracking during generation
# ============================================================


class TestProgressTrackingEndpoint:
    """Given a POV generation task is currently executing,
    GET /api/v1/pov/job/{job_id}/progress returns step-level progress."""

    @pytest.mark.asyncio
    async def test_progress_returns_current_step(self) -> None:
        """Progress shows current step number and name."""
        job_data = {
            "status": "running",
            "progress": {
                "current_step": 3,
                "step_name": "Cross-Source Triangulation",
                "completion_percentage": 37,
                "total_steps": 8,
            },
        }
        request = _make_mock_request(job_data)
        user = _make_mock_user()

        result = await get_job_progress("job-123", request, user)

        assert result["current_step"] == 3
        assert result["step_name"] == "Cross-Source Triangulation"
        assert result["completion_percentage"] == 37

    @pytest.mark.asyncio
    async def test_progress_returns_task_id(self) -> None:
        """Progress response includes the task_id."""
        job_data = {
            "status": "running",
            "progress": {"current_step": 1, "step_name": "Evidence Aggregation",
                         "completion_percentage": 12, "total_steps": 8},
        }
        request = _make_mock_request(job_data)
        user = _make_mock_user()

        result = await get_job_progress("job-abc", request, user)
        assert result["task_id"] == "job-abc"

    @pytest.mark.asyncio
    async def test_progress_completed_shows_100_percent(self) -> None:
        """Completed job shows 100% progress."""
        job_data = {
            "status": "completed",
            "progress": {
                "current_step": 8,
                "step_name": "Complete",
                "completion_percentage": 100,
                "total_steps": 8,
            },
        }
        request = _make_mock_request(job_data)
        user = _make_mock_user()

        result = await get_job_progress("job-done", request, user)

        assert result["completion_percentage"] == 100
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_progress_not_found_raises_404(self) -> None:
        """Missing job returns 404."""
        from fastapi import HTTPException

        request = _make_mock_request(None)
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_job_progress("nonexistent", request, user)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_progress_includes_failed_step(self) -> None:
        """Failed job includes failed_step details."""
        job_data = {
            "status": "failed",
            "progress": {
                "current_step": 3,
                "step_name": "Cross-Source Triangulation",
                "completion_percentage": 25,
                "total_steps": 8,
                "failed_step": {
                    "step_number": 3,
                    "step_name": "Cross-Source Triangulation",
                    "error": "Timeout",
                },
            },
        }
        request = _make_mock_request(job_data)
        user = _make_mock_user()

        result = await get_job_progress("job-fail", request, user)

        assert result["failed_step"] is not None
        assert result["failed_step"]["step_number"] == 3
        assert "Timeout" in result["failed_step"]["error"]

    @pytest.mark.asyncio
    async def test_progress_includes_completed_steps_list(self) -> None:
        """Progress includes list of completed steps with timing."""
        job_data = {
            "status": "running",
            "progress": {
                "current_step": 2,
                "step_name": "Entity Extraction",
                "completion_percentage": 25,
                "total_steps": 8,
                "completed_steps": [
                    {"step_number": 1, "step_name": "Evidence Aggregation", "duration_ms": 120},
                    {"step_number": 2, "step_name": "Entity Extraction", "duration_ms": 340},
                ],
            },
        }
        request = _make_mock_request(job_data)
        user = _make_mock_user()

        result = await get_job_progress("job-steps", request, user)

        assert result["completed_steps"] is not None
        assert len(result["completed_steps"]) == 2

    @pytest.mark.asyncio
    async def test_progress_total_duration_tracked(self) -> None:
        """Progress includes total pipeline duration."""
        job_data = {
            "status": "completed",
            "progress": {
                "current_step": 8,
                "step_name": "Complete",
                "completion_percentage": 100,
                "total_steps": 8,
                "total_duration_ms": 5432,
            },
        }
        request = _make_mock_request(job_data)
        user = _make_mock_user()

        result = await get_job_progress("job-timed", request, user)
        assert result["total_duration_ms"] == 5432


# ============================================================
# Scenario 5: POV version history
# ============================================================


class TestVersionHistoryEndpoint:
    """Given multiple POV versions exist for an engagement,
    GET /api/v1/pov/engagement/{id}/versions returns the history."""

    @pytest.mark.asyncio
    async def test_version_history_returns_all_versions(self) -> None:
        """All versions returned ordered by version descending."""
        eng_id = uuid.uuid4()
        model_v2 = _make_mock_model(engagement_id=eng_id, version=2,
                                     confidence_score=0.85, element_count=10)
        model_v1 = _make_mock_model(engagement_id=eng_id, version=1,
                                     confidence_score=0.7, element_count=8)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [model_v2, model_v1]
        session.execute = AsyncMock(return_value=mock_result)

        user = _make_mock_user(UserRole.PLATFORM_ADMIN)

        result = await get_version_history(str(eng_id), False, session, user)

        assert result["total_versions"] == 2
        assert result["versions"][0]["version"] == 2
        assert result["versions"][1]["version"] == 1

    @pytest.mark.asyncio
    async def test_version_history_includes_engagement_id(self) -> None:
        """Response includes the engagement_id."""
        eng_id = uuid.uuid4()
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        user = _make_mock_user(UserRole.PLATFORM_ADMIN)

        result = await get_version_history(str(eng_id), False, session, user)
        assert result["engagement_id"] == str(eng_id)

    @pytest.mark.asyncio
    async def test_version_history_empty_engagement(self) -> None:
        """Engagement with no POVs returns empty list."""
        eng_id = uuid.uuid4()
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        user = _make_mock_user(UserRole.PLATFORM_ADMIN)

        result = await get_version_history(str(eng_id), False, session, user)
        assert result["total_versions"] == 0
        assert result["versions"] == []

    @pytest.mark.asyncio
    async def test_version_history_invalid_engagement_id(self) -> None:
        """Invalid engagement ID returns 400."""
        from fastapi import HTTPException

        session = AsyncMock()
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_version_history("not-a-uuid", False, session, user)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_version_history_no_diff_by_default(self) -> None:
        """Diff is None when include_diff=False."""
        eng_id = uuid.uuid4()
        model_v1 = _make_mock_model(engagement_id=eng_id, version=1)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [model_v1]
        session.execute = AsyncMock(return_value=mock_result)

        user = _make_mock_user(UserRole.PLATFORM_ADMIN)

        result = await get_version_history(str(eng_id), False, session, user)
        assert result["diff"] is None

    @pytest.mark.asyncio
    async def test_version_summary_fields(self) -> None:
        """Each version summary has required fields."""
        eng_id = uuid.uuid4()
        model = _make_mock_model(
            engagement_id=eng_id, version=3,
            confidence_score=0.88, element_count=12,
        )

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [model]
        session.execute = AsyncMock(return_value=mock_result)

        user = _make_mock_user(UserRole.PLATFORM_ADMIN)

        result = await get_version_history(str(eng_id), False, session, user)

        v = result["versions"][0]
        assert v["version"] == 3
        assert v["confidence_score"] == 0.88
        assert v["element_count"] == 12
        assert "model_id" in v
        assert "status" in v

    @pytest.mark.asyncio
    async def test_version_history_include_diff(self) -> None:
        """include_diff=True computes diff between latest two versions."""
        from unittest.mock import patch

        eng_id = uuid.uuid4()
        model_v2 = _make_mock_model(engagement_id=eng_id, version=2,
                                     confidence_score=0.85, element_count=10)
        model_v1 = _make_mock_model(engagement_id=eng_id, version=1,
                                     confidence_score=0.7, element_count=8)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [model_v2, model_v1]
        session.execute = AsyncMock(return_value=mock_result)

        user = _make_mock_user(UserRole.PLATFORM_ADMIN)

        fake_diff = {
            "added_count": 2,
            "removed_count": 1,
            "changed_count": 0,
            "unchanged_count": 5,
            "added": ["NewTask"],
            "removed": ["OldTask"],
            "changed": [],
        }

        with patch(
            "src.api.routes.pov._get_elements_for_model",
            new_callable=AsyncMock,
            return_value=[{"name": "A", "confidence_score": 0.8}],
        ), patch(
            "src.api.routes.pov.compute_version_diff",
            return_value=fake_diff,
        ):
            result = await get_version_history(str(eng_id), True, session, user)

        assert result["diff"] is not None
        assert result["diff"]["added_count"] == 2
        assert result["diff"]["removed_count"] == 1

    @pytest.mark.asyncio
    async def test_version_history_non_member_gets_403(self) -> None:
        """Non-admin, non-member user receives 403 Forbidden."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        session = AsyncMock()

        # First execute call is the membership check — returns None (not a member)
        membership_result = MagicMock()
        membership_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=membership_result)

        user = _make_mock_user(UserRole.ENGAGEMENT_LEAD)

        with pytest.raises(HTTPException) as exc_info:
            await get_version_history(str(eng_id), False, session, user)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_version_history_member_can_access(self) -> None:
        """Engagement member (non-admin) can access version history."""
        eng_id = uuid.uuid4()
        model_v1 = _make_mock_model(engagement_id=eng_id, version=1)

        # Membership check returns a member record; version query returns models
        membership_result = MagicMock()
        membership_result.scalar_one_or_none.return_value = MagicMock()  # member exists

        version_result = MagicMock()
        version_result.scalars.return_value.all.return_value = [model_v1]

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[membership_result, version_result])

        user = _make_mock_user(UserRole.ENGAGEMENT_LEAD)

        result = await get_version_history(str(eng_id), False, session, user)
        assert result["total_versions"] == 1


# ============================================================
# Schema validation tests
# ============================================================


class TestProgressResponseSchema:
    """ProgressResponse schema validation."""

    def test_progress_response_validates(self) -> None:
        """ProgressResponse can be constructed with valid data."""
        resp = ProgressResponse(
            task_id="job-123",
            status="running",
            current_step=3,
            step_name="Cross-Source Triangulation",
            completion_percentage=37,
        )
        assert resp.task_id == "job-123"
        assert resp.total_steps == 8

    def test_progress_response_defaults(self) -> None:
        """ProgressResponse has sensible defaults."""
        resp = ProgressResponse(
            task_id="x", status="pending",
            current_step=0, step_name="", completion_percentage=0,
        )
        assert resp.total_steps == 8
        assert resp.total_duration_ms == 0
        assert resp.completed_steps is None
        assert resp.failed_step is None


class TestVersionHistoryResponseSchema:
    """VersionHistoryResponse schema validation."""

    def test_version_history_validates(self) -> None:
        """VersionHistoryResponse can be constructed."""
        resp = VersionHistoryResponse(
            engagement_id="eng-1",
            versions=[],
            total_versions=0,
        )
        assert resp.engagement_id == "eng-1"
        assert resp.diff is None

    def test_version_diff_response_validates(self) -> None:
        """VersionDiffResponse fields are all present."""
        from src.api.routes.pov import VersionDiffResponse

        diff = VersionDiffResponse(
            added_count=2, removed_count=1,
            changed_count=3, unchanged_count=4,
            added=["X", "Y"], removed=["Z"], changed=["A", "B", "C"],
        )
        assert diff.added_count == 2
        assert len(diff.changed) == 3


# ============================================================
# Integration: generate endpoint stores progress
# ============================================================


class TestGenerateStoresProgress:
    """The POST /generate endpoint stores progress data in Redis."""

    @pytest.mark.asyncio
    async def test_initial_job_has_progress(self) -> None:
        """Job stored in Redis includes progress field."""
        from src.api.routes.pov import _set_job

        request = MagicMock()
        redis = AsyncMock()
        request.app.state.redis_client = redis

        initial_data = {
            "status": "running",
            "progress": {
                "current_step": 0,
                "step_name": "Evidence Aggregation",
                "completion_percentage": 0,
                "total_steps": 8,
            },
        }

        await _set_job(request, "job-init", initial_data)

        # Verify Redis setex was called with progress data
        call_args = redis.setex.call_args
        stored = json.loads(call_args[0][2])
        assert stored["progress"]["total_steps"] == 8
        assert stored["progress"]["current_step"] == 0


# ============================================================
# Helper function tests
# ============================================================


class TestGetElementsForModel:
    """Tests for the _get_elements_for_model helper."""

    @pytest.mark.asyncio
    async def test_returns_name_and_confidence(self) -> None:
        """Returns elements as dicts with name and confidence_score."""
        elem = MagicMock()
        elem.name = "Submit"
        elem.confidence_score = 0.9

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [elem]
        session.execute = AsyncMock(return_value=mock_result)

        elements = await _get_elements_for_model(session, uuid.uuid4())

        assert len(elements) == 1
        assert elements[0]["name"] == "Submit"
        assert elements[0]["confidence_score"] == 0.9

    @pytest.mark.asyncio
    async def test_empty_model_returns_empty_list(self) -> None:
        """Model with no elements returns empty list."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        elements = await _get_elements_for_model(session, uuid.uuid4())
        assert elements == []
