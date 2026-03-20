"""Tests for the task queue API routes (src/api/routes/tasks.py).

Verifies the tasks router is mounted at /api/v1/tasks (Audit Batch 1 CRITICAL fix).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.tasks import TaskProgress, TaskStatus


@pytest.fixture(autouse=True)
def _setup_task_queue(test_app: MagicMock) -> None:
    """Set up a mock task queue on the test app."""
    mock_queue = MagicMock()
    mock_queue.registered_types = {"pov_generation", "evidence_batch", "gdpr_erasure"}
    mock_queue.enqueue = AsyncMock(return_value="task-123")
    mock_queue.get_status = AsyncMock(
        return_value=TaskProgress(
            task_id="task-123",
            task_type="pov_generation",
            status=TaskStatus.PENDING,
            current_step=0,
            total_steps=1,
            percent_complete=0,
        )
    )
    test_app.state.task_queue = mock_queue


class TestTasksRouterPrefix:
    """Verify the tasks router is at /api/v1/tasks (not /tasks)."""

    @pytest.mark.asyncio
    async def test_submit_reachable_at_api_v1(self, client: AsyncClient) -> None:
        """POST /api/v1/tasks/submit should be reachable (not 404)."""
        response = await client.post(
            "/api/v1/tasks/submit",
            json={"task_type": "pov_generation", "payload": {}},
        )
        # 202 Accepted (or 403 if permission denied, but NOT 404)
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_status_reachable_at_api_v1(self, client: AsyncClient) -> None:
        """GET /api/v1/tasks/{id} should be reachable."""
        response = await client.get("/api/v1/tasks/task-123")
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_old_prefix_not_reachable(self, client: AsyncClient) -> None:
        """POST /tasks/submit should return 404 (old prefix removed)."""
        response = await client.post(
            "/tasks/submit",
            json={"task_type": "pov_generation", "payload": {}},
        )
        assert response.status_code == 404
