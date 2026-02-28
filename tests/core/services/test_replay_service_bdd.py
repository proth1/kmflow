"""BDD tests for replay service (Story #345).

Tests task creation, frame generation, and pagination.
"""

from __future__ import annotations

from src.core.services.replay_service import (
    ReplayType,
    clear_task_store,
    create_aggregate_task,
    create_single_case_task,
    create_variant_comparison_task,
    get_task,
    get_task_frames,
)


class TestSingleCaseReplayTask:
    """Scenario 1: Single-Case Replay Task Creation."""

    def setup_method(self) -> None:
        clear_task_store()

    def test_creates_task_with_pending_response(self) -> None:
        """Task is created and stored with correct type."""
        task = create_single_case_task("CASE-001")

        assert task.id
        assert task.replay_type == ReplayType.SINGLE_CASE
        assert task.params["case_id"] == "CASE-001"

    def test_task_has_frames(self) -> None:
        """Created task has replay frames."""
        task = create_single_case_task("CASE-001")

        assert len(task.frames) == 20
        assert task.frames[0].frame_index == 0
        assert task.frames[19].frame_index == 19

    def test_task_retrievable_by_id(self) -> None:
        """Task can be retrieved from the store."""
        task = create_single_case_task("CASE-001")

        retrieved = get_task(task.id)
        assert retrieved is not None
        assert retrieved.id == task.id

    def test_created_at_is_set(self) -> None:
        """Task has a created_at timestamp."""
        task = create_single_case_task("CASE-001")
        assert task.created_at
        assert "2026" in task.created_at or "T" in task.created_at


class TestPaginatedFrameRetrieval:
    """Scenario 2: Paginated Frame Retrieval."""

    def setup_method(self) -> None:
        clear_task_store()

    def test_first_page_of_frames(self) -> None:
        """First 10 frames returned with has_more=true."""
        task = create_single_case_task("CASE-002")

        result = get_task_frames(task.id, limit=10, offset=0)
        assert result is not None
        assert len(result["frames"]) == 10
        assert result["total"] == 20
        assert result["limit"] == 10
        assert result["offset"] == 0
        assert result["has_more"] is True

    def test_second_page_of_frames(self) -> None:
        """Second page returns remaining frames."""
        task = create_single_case_task("CASE-002")

        result = get_task_frames(task.id, limit=10, offset=10)
        assert result is not None
        assert len(result["frames"]) == 10
        assert result["offset"] == 10
        assert result["has_more"] is False

    def test_last_page_partial(self) -> None:
        """Offset near end returns partial page."""
        task = create_single_case_task("CASE-002")

        result = get_task_frames(task.id, limit=10, offset=15)
        assert result is not None
        assert len(result["frames"]) == 5
        assert result["has_more"] is False

    def test_frame_data_structure(self) -> None:
        """Each frame has expected fields."""
        task = create_single_case_task("CASE-002")

        result = get_task_frames(task.id, limit=1, offset=0)
        assert result is not None
        frame = result["frames"][0]
        assert "frame_index" in frame
        assert "timestamp" in frame
        assert "active_elements" in frame
        assert "completed_elements" in frame
        assert "metrics" in frame

    def test_unknown_task_returns_none(self) -> None:
        """Unknown task ID returns None."""
        result = get_task_frames("nonexistent", limit=10, offset=0)
        assert result is None


class TestVariantComparisonTask:
    """Scenario 3: Variant Comparison Task Creation."""

    def setup_method(self) -> None:
        clear_task_store()

    def test_creates_comparison_task(self) -> None:
        """Comparison task is created with both variant IDs."""
        task = create_variant_comparison_task("var-A", "var-B")

        assert task.id
        assert task.replay_type == ReplayType.VARIANT_COMPARISON
        assert task.params["variant_a_id"] == "var-A"
        assert task.params["variant_b_id"] == "var-B"

    def test_comparison_has_frames(self) -> None:
        """Comparison task produces frames."""
        task = create_variant_comparison_task("var-A", "var-B")
        assert len(task.frames) == 10


class TestAggregateTask:
    """Aggregate volume replay task creation."""

    def setup_method(self) -> None:
        clear_task_store()

    def test_creates_aggregate_task(self) -> None:
        task = create_aggregate_task(
            engagement_id="eng-1",
            time_range_start="2026-01-01",
            time_range_end="2026-01-31",
            interval_granularity="daily",
        )

        assert task.id
        assert task.replay_type == ReplayType.AGGREGATE
        assert task.params["engagement_id"] == "eng-1"
        assert task.params["interval_granularity"] == "daily"

    def test_aggregate_has_frames(self) -> None:
        task = create_aggregate_task("eng-1", "2026-01-01", "2026-01-31")
        assert len(task.frames) == 15


class TestGetTask:
    """Task retrieval."""

    def setup_method(self) -> None:
        clear_task_store()

    def test_get_unknown_task_returns_none(self) -> None:
        result = get_task("nonexistent")
        assert result is None

    def test_to_status_dict(self) -> None:
        task = create_single_case_task("CASE-003")
        d = task.to_status_dict()
        assert d["task_id"] == task.id
        assert d["replay_type"] == "single_case"
        assert "status" in d
        assert "progress_pct" in d
        assert "created_at" in d
