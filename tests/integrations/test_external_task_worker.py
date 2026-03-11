"""Tests for ExternalTaskWorker."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.integrations.camunda import CamundaClient
from src.integrations.external_task_worker import ExternalTaskWorker


@pytest.fixture
def mock_client() -> AsyncMock:
    client = AsyncMock(spec=CamundaClient)
    client.fetch_and_lock_external_tasks = AsyncMock(return_value=[])
    client.complete_external_task = AsyncMock()
    client.fail_external_task = AsyncMock()
    return client


@pytest.fixture
def worker(mock_client: AsyncMock) -> ExternalTaskWorker:
    return ExternalTaskWorker(
        client=mock_client,
        worker_id="test-worker",
        poll_interval=0.01,  # Fast polling for tests
    )


class TestRegistration:
    def test_register_handler(self, worker: ExternalTaskWorker) -> None:
        async def handler(task: dict) -> dict:
            return {}

        worker.register("test-topic", handler)
        assert "test-topic" in worker._handlers

    def test_register_multiple_handlers(self, worker: ExternalTaskWorker) -> None:
        worker.register("topic-a", AsyncMock())
        worker.register("topic-b", AsyncMock())
        assert len(worker._handlers) == 2


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_creates_task(self, worker: ExternalTaskWorker) -> None:
        worker.register("test", AsyncMock())
        await worker.start()
        assert worker._running is True
        assert worker._task is not None
        await worker.stop()
        assert worker._running is False

    @pytest.mark.asyncio
    async def test_start_without_handlers_does_nothing(self, worker: ExternalTaskWorker) -> None:
        await worker.start()
        assert worker._running is False
        assert worker._task is None

    @pytest.mark.asyncio
    async def test_double_start_is_idempotent(self, worker: ExternalTaskWorker) -> None:
        worker.register("test", AsyncMock())
        await worker.start()
        task1 = worker._task
        await worker.start()  # Should not create a second task
        assert worker._task is task1
        await worker.stop()


class TestPollOnce:
    @pytest.mark.asyncio
    async def test_completes_task_on_handler_success(self, worker: ExternalTaskWorker, mock_client: AsyncMock) -> None:
        handler = AsyncMock(return_value={"result": "done"})
        worker.register("classify", handler)

        mock_client.fetch_and_lock_external_tasks.return_value = [
            {"id": "task-1", "topicName": "classify", "retries": 3}
        ]

        await worker._poll_once()

        handler.assert_awaited_once()
        mock_client.complete_external_task.assert_awaited_once_with(
            task_id="task-1",
            worker_id="test-worker",
            variables={"result": "done"},
        )

    @pytest.mark.asyncio
    async def test_reports_failure_on_handler_error(self, worker: ExternalTaskWorker, mock_client: AsyncMock) -> None:
        handler = AsyncMock(side_effect=ValueError("processing failed"))
        worker.register("classify", handler)

        mock_client.fetch_and_lock_external_tasks.return_value = [
            {"id": "task-1", "topicName": "classify", "retries": 3}
        ]

        await worker._poll_once()

        mock_client.fail_external_task.assert_awaited_once()
        call_kwargs = mock_client.fail_external_task.call_args[1]
        assert call_kwargs["task_id"] == "task-1"
        assert call_kwargs["retries"] == 2  # 3 - 1

    @pytest.mark.asyncio
    async def test_retries_decrement_to_zero(self, worker: ExternalTaskWorker, mock_client: AsyncMock) -> None:
        worker.register("topic", AsyncMock(side_effect=RuntimeError("fail")))
        mock_client.fetch_and_lock_external_tasks.return_value = [{"id": "t1", "topicName": "topic", "retries": 1}]

        await worker._poll_once()

        call_kwargs = mock_client.fail_external_task.call_args[1]
        assert call_kwargs["retries"] == 0

    @pytest.mark.asyncio
    async def test_no_handler_for_topic_skips(self, worker: ExternalTaskWorker, mock_client: AsyncMock) -> None:
        worker.register("other-topic", AsyncMock())
        mock_client.fetch_and_lock_external_tasks.return_value = [{"id": "t1", "topicName": "unknown-topic"}]

        await worker._poll_once()

        mock_client.complete_external_task.assert_not_awaited()
        mock_client.fail_external_task.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handles_fetch_error_gracefully(self, worker: ExternalTaskWorker, mock_client: AsyncMock) -> None:
        worker.register("topic", AsyncMock())
        mock_client.fetch_and_lock_external_tasks.side_effect = ConnectionError("offline")

        # Should not raise
        await worker._poll_once()

    @pytest.mark.asyncio
    async def test_processes_multiple_tasks(self, worker: ExternalTaskWorker, mock_client: AsyncMock) -> None:
        handler = AsyncMock(return_value={})
        worker.register("batch", handler)

        mock_client.fetch_and_lock_external_tasks.return_value = [
            {"id": "t1", "topicName": "batch", "retries": 3},
            {"id": "t2", "topicName": "batch", "retries": 3},
        ]

        await worker._poll_once()

        assert handler.await_count == 2
        assert mock_client.complete_external_task.await_count == 2
