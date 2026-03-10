"""Tests for task status API routes (KMFLOW-58).

Tests POST /api/v1/tasks/submit and GET /api/v1/tasks/{task_id} endpoints.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.api.routes.tasks import _get_task_queue, _progress_to_response
from src.core.tasks.base import TaskStatus
from src.core.tasks.queue import TaskProgress


class TestProgressToResponse:
    """Unit tests for the progress-to-response serializer."""

    def test_completed_task(self) -> None:
        p = TaskProgress(
            task_id="abc-123",
            task_type="pov_generation",
            status=TaskStatus.COMPLETED,
            current_step=8,
            total_steps=8,
            percent_complete=100,
            result={"pov_id": "pov-1"},
            created_at="2026-03-09T12:00:00",
            completed_at="2026-03-09T12:01:00",
        )
        resp = _progress_to_response(p)

        assert resp["task_id"] == "abc-123"
        assert resp["status"] == "COMPLETED"
        assert resp["percent_complete"] == 100
        assert resp["result"]["pov_id"] == "pov-1"

    def test_pending_task(self) -> None:
        p = TaskProgress(task_id="def-456", task_type="evidence_batch")
        resp = _progress_to_response(p)

        assert resp["status"] == "PENDING"
        assert resp["percent_complete"] == 0
        assert resp["error"] == ""

    def test_failed_task_includes_error(self) -> None:
        p = TaskProgress(
            task_id="ghi-789",
            task_type="gdpr_erasure",
            status=TaskStatus.FAILED,
            error="Database connection lost",
            attempt_count=3,
        )
        resp = _progress_to_response(p)

        assert resp["status"] == "FAILED"
        assert resp["error"] == "Database connection lost"
        assert resp["attempt_count"] == 3


class TestGetTaskQueue:
    """Unit tests for the task queue dependency."""

    def test_raises_503_when_queue_unavailable(self) -> None:
        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # no task_queue attribute

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _get_task_queue(request)
        assert exc_info.value.status_code == 503
