"""BDD tests for POV Generation Orchestrator (Story #318).

Tests async task creation, progress tracking, result retrieval,
partial result preservation, and version diffing.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.pov.orchestrator import (
    POV_STEPS,
    TOTAL_STEPS,
    PovGenerationState,
    PovGenerationWorker,
    PovStepResult,
    compute_version_diff,
    get_step_info,
)

# --- Scenario 1: Async POV generation task creation -------------------------


class TestAsyncPovGeneration:
    """Scenario 1: POST returns 202 with task_id, task enqueued."""

    def test_worker_has_pov_generation_task_type(self) -> None:
        """PovGenerationWorker task_type is 'pov_generation'."""
        worker = PovGenerationWorker()
        assert worker.task_type == "pov_generation"

    def test_worker_max_retries_is_one(self) -> None:
        """POV generation does not auto-retry (expensive operation)."""
        worker = PovGenerationWorker()
        assert worker.max_retries == 1

    @pytest.mark.asyncio
    async def test_execute_returns_result_with_engagement(self) -> None:
        """Successful execution returns result with engagement_id."""
        worker = PovGenerationWorker()
        result = await worker.execute({"engagement_id": "eng-001"})

        assert result["engagement_id"] == "eng-001"
        assert result["status"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_execute_requires_engagement_id(self) -> None:
        """Missing engagement_id raises ValueError."""
        worker = PovGenerationWorker()

        with pytest.raises(ValueError, match="engagement_id is required"):
            await worker.execute({})

    @pytest.mark.asyncio
    async def test_execute_uses_default_scope(self) -> None:
        """Default scope is 'all'."""
        worker = PovGenerationWorker()
        result = await worker.execute({"engagement_id": "eng-001"})

        # All completed steps should have scope="all"
        for step in result["completed_steps"]:
            assert step["data"]["scope"] == "all"

    @pytest.mark.asyncio
    async def test_execute_with_custom_scope(self) -> None:
        """Custom scope is passed through to steps."""
        worker = PovGenerationWorker()
        result = await worker.execute({"engagement_id": "eng-001", "scope": "finance"})

        for step in result["completed_steps"]:
            assert step["data"]["scope"] == "finance"


# --- Scenario 2: Progress tracking during generation -----------------------


class TestProgressTracking:
    """Scenario 2: Progress visible via get_status."""

    @pytest.mark.asyncio
    async def test_all_8_steps_completed(self) -> None:
        """Successful run completes all 8 consensus steps."""
        worker = PovGenerationWorker()
        result = await worker.execute({"engagement_id": "eng-001"})

        assert len(result["completed_steps"]) == 8
        assert result["current_step"] == 8
        assert result["total_steps"] == 8

    @pytest.mark.asyncio
    async def test_completion_percentage_at_100(self) -> None:
        """Completed POV has 100% completion."""
        worker = PovGenerationWorker()
        result = await worker.execute({"engagement_id": "eng-001"})

        assert result["completion_percentage"] == 100

    @pytest.mark.asyncio
    async def test_step_names_match_consensus_algorithm(self) -> None:
        """Step names match the defined consensus algorithm steps."""
        worker = PovGenerationWorker()
        result = await worker.execute({"engagement_id": "eng-001"})

        expected_names = [s["name"] for s in POV_STEPS]
        actual_names = [s["step_name"] for s in result["completed_steps"]]
        assert actual_names == expected_names

    @pytest.mark.asyncio
    async def test_step_durations_tracked(self) -> None:
        """Each step has a duration_ms measurement."""
        worker = PovGenerationWorker()
        result = await worker.execute({"engagement_id": "eng-001"})

        for step in result["completed_steps"]:
            assert "duration_ms" in step
            assert isinstance(step["duration_ms"], int)

    @pytest.mark.asyncio
    async def test_total_duration_tracked(self) -> None:
        """Total pipeline duration is recorded."""
        worker = PovGenerationWorker()
        result = await worker.execute({"engagement_id": "eng-001"})

        assert result["total_duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_progress_reports_called(self) -> None:
        """Worker calls report_progress for each step."""
        worker = PovGenerationWorker()
        await worker.execute({"engagement_id": "eng-001"})

        # After completion, progress should show final state
        progress = worker.progress
        assert progress["current_step"] == 8
        assert progress["total_steps"] == 8
        assert progress["percent_complete"] == 100


# --- Scenario 3: Successful POV retrieval -----------------------------------


class TestPovRetrieval:
    """Scenario 3: Completed task has full result payload."""

    @pytest.mark.asyncio
    async def test_completed_status(self) -> None:
        """Completed POV has status=COMPLETED."""
        worker = PovGenerationWorker()
        result = await worker.execute({"engagement_id": "eng-001"})

        assert result["status"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_version_in_result(self) -> None:
        """Result includes version number."""
        worker = PovGenerationWorker()
        result = await worker.execute({"engagement_id": "eng-001", "version": 3})

        assert result["version"] == 3

    @pytest.mark.asyncio
    async def test_partial_data_accumulated(self) -> None:
        """All 8 steps have partial data entries."""
        worker = PovGenerationWorker()
        result = await worker.execute({"engagement_id": "eng-001"})

        for i in range(1, 9):
            key = f"step_{i}"
            assert key in result["partial_data"]
            assert result["partial_data"][key]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_no_failed_step(self) -> None:
        """Successful generation has no failed_step."""
        worker = PovGenerationWorker()
        result = await worker.execute({"engagement_id": "eng-001"})

        assert result["failed_step"] is None


# --- Scenario 4: Partial result preservation on failure ----------------------


class TestPartialResultPreservation:
    """Scenario 4: Failed steps preserve completed results."""

    @pytest.mark.asyncio
    async def test_failed_partial_status(self) -> None:
        """Step failure sets FAILED_PARTIAL status."""

        class FailAtStep3Worker(PovGenerationWorker):
            async def _execute_step(
                self,
                step_number: int,
                engagement_id: str,
                scope: str,
                state: PovGenerationState,
            ) -> dict[str, Any]:
                if step_number == 3:
                    raise RuntimeError("Triangulation engine error")
                return await super()._execute_step(step_number, engagement_id, scope, state)

        worker = FailAtStep3Worker()
        result = await worker.execute({"engagement_id": "eng-001"})

        assert result["status"] == "FAILED_PARTIAL"

    @pytest.mark.asyncio
    async def test_completed_steps_preserved(self) -> None:
        """Steps completed before failure are preserved."""

        class FailAtStep3Worker(PovGenerationWorker):
            async def _execute_step(
                self,
                step_number: int,
                engagement_id: str,
                scope: str,
                state: PovGenerationState,
            ) -> dict[str, Any]:
                if step_number == 3:
                    raise RuntimeError("Triangulation engine error")
                return await super()._execute_step(step_number, engagement_id, scope, state)

        worker = FailAtStep3Worker()
        result = await worker.execute({"engagement_id": "eng-001"})

        assert len(result["completed_steps"]) == 2
        assert result["completed_steps"][0]["step_name"] == "Evidence Aggregation"
        assert result["completed_steps"][1]["step_name"] == "Entity Extraction"

    @pytest.mark.asyncio
    async def test_failed_step_recorded(self) -> None:
        """The failing step is recorded with error details."""

        class FailAtStep3Worker(PovGenerationWorker):
            async def _execute_step(
                self,
                step_number: int,
                engagement_id: str,
                scope: str,
                state: PovGenerationState,
            ) -> dict[str, Any]:
                if step_number == 3:
                    raise RuntimeError("Triangulation engine error")
                return await super()._execute_step(step_number, engagement_id, scope, state)

        worker = FailAtStep3Worker()
        result = await worker.execute({"engagement_id": "eng-001"})

        assert result["failed_step"] is not None
        assert result["failed_step"]["step_number"] == 3
        assert result["failed_step"]["step_name"] == "Cross-Source Triangulation"
        assert "Triangulation engine error" in result["failed_step"]["error"]

    @pytest.mark.asyncio
    async def test_partial_data_preserved_up_to_failure(self) -> None:
        """Partial data is preserved for steps that completed."""

        class FailAtStep5Worker(PovGenerationWorker):
            async def _execute_step(
                self,
                step_number: int,
                engagement_id: str,
                scope: str,
                state: PovGenerationState,
            ) -> dict[str, Any]:
                if step_number == 5:
                    raise RuntimeError("Contradiction resolver timeout")
                return await super()._execute_step(step_number, engagement_id, scope, state)

        worker = FailAtStep5Worker()
        result = await worker.execute({"engagement_id": "eng-001"})

        # Steps 1-4 completed
        assert len(result["completed_steps"]) == 4
        assert "step_1" in result["partial_data"]
        assert "step_4" in result["partial_data"]
        # Step 5 did not complete
        assert "step_5" not in result["partial_data"]

    @pytest.mark.asyncio
    async def test_failure_at_first_step(self) -> None:
        """Failure at step 1 produces empty completed_steps."""

        class FailAtStep1Worker(PovGenerationWorker):
            async def _execute_step(
                self,
                step_number: int,
                engagement_id: str,
                scope: str,
                state: PovGenerationState,
            ) -> dict[str, Any]:
                if step_number == 1:
                    raise RuntimeError("No evidence found")
                return await super()._execute_step(step_number, engagement_id, scope, state)

        worker = FailAtStep1Worker()
        result = await worker.execute({"engagement_id": "eng-001"})

        assert result["status"] == "FAILED_PARTIAL"
        assert len(result["completed_steps"]) == 0
        assert result["failed_step"]["step_number"] == 1


# --- Scenario 5: POV versioning --------------------------------------------


class TestPovVersioning:
    """Scenario 5: Version diff between POV generations."""

    def test_version_diff_added_elements(self) -> None:
        """New elements in v2 are counted as added."""
        old = [{"name": "A", "confidence_score": 0.8}]
        new = [
            {"name": "A", "confidence_score": 0.8},
            {"name": "B", "confidence_score": 0.7},
        ]
        diff = compute_version_diff(old, new)

        assert diff["added_count"] == 1
        assert "B" in diff["added"]

    def test_version_diff_removed_elements(self) -> None:
        """Elements missing in v2 are counted as removed."""
        old = [
            {"name": "A", "confidence_score": 0.8},
            {"name": "B", "confidence_score": 0.7},
        ]
        new = [{"name": "A", "confidence_score": 0.8}]
        diff = compute_version_diff(old, new)

        assert diff["removed_count"] == 1
        assert "B" in diff["removed"]

    def test_version_diff_changed_elements(self) -> None:
        """Elements with different confidence scores are changed."""
        old = [{"name": "A", "confidence_score": 0.6}]
        new = [{"name": "A", "confidence_score": 0.9}]
        diff = compute_version_diff(old, new)

        assert diff["changed_count"] == 1
        assert "A" in diff["changed"]

    def test_version_diff_unchanged_elements(self) -> None:
        """Elements with same confidence are unchanged."""
        old = [{"name": "A", "confidence_score": 0.8}]
        new = [{"name": "A", "confidence_score": 0.8}]
        diff = compute_version_diff(old, new)

        assert diff["unchanged_count"] == 1
        assert diff["changed_count"] == 0

    def test_version_diff_empty_old(self) -> None:
        """First version has all elements as added."""
        diff = compute_version_diff(
            [],
            [{"name": "A"}, {"name": "B"}],
        )

        assert diff["added_count"] == 2
        assert diff["removed_count"] == 0

    def test_version_diff_empty_new(self) -> None:
        """Clearing all elements shows all as removed."""
        diff = compute_version_diff(
            [{"name": "A"}, {"name": "B"}],
            [],
        )

        assert diff["removed_count"] == 2
        assert diff["added_count"] == 0

    def test_version_diff_complex(self) -> None:
        """Complex diff with mixed changes."""
        old = [
            {"name": "A", "confidence_score": 0.8},
            {"name": "B", "confidence_score": 0.6},
            {"name": "C", "confidence_score": 0.5},
        ]
        new = [
            {"name": "A", "confidence_score": 0.8},  # unchanged
            {"name": "B", "confidence_score": 0.9},  # changed
            {"name": "D", "confidence_score": 0.7},  # added (C removed)
        ]
        diff = compute_version_diff(old, new)

        assert diff["unchanged_count"] == 1
        assert diff["changed_count"] == 1
        assert diff["added_count"] == 1
        assert diff["removed_count"] == 1
        assert "D" in diff["added"]
        assert "C" in diff["removed"]
        assert "B" in diff["changed"]


# --- PovGenerationState tests -----------------------------------------------


class TestPovGenerationState:
    """PovGenerationState data structure."""

    def test_initial_state(self) -> None:
        """New state has zero progress."""
        state = PovGenerationState(engagement_id="eng-001")

        assert state.current_step == 0
        assert state.completion_percentage == 0
        assert state.step_name == "Evidence Aggregation"

    def test_step_progression(self) -> None:
        """State tracks step progression correctly."""
        state = PovGenerationState(engagement_id="eng-001")
        state.completed_steps.append(
            PovStepResult(step_number=1, step_name="Evidence Aggregation"),
        )

        assert state.current_step == 1
        assert state.step_name == "Entity Extraction"
        assert state.completion_percentage == 12  # 1/8 * 100 = 12.5 → 12

    def test_completed_state(self) -> None:
        """Fully completed state has 100% and 'Complete' step name."""
        state = PovGenerationState(engagement_id="eng-001")
        for i, step_def in enumerate(POV_STEPS):
            state.completed_steps.append(
                PovStepResult(step_number=i + 1, step_name=step_def["name"]),
            )

        assert state.current_step == 8
        assert state.completion_percentage == 100
        assert state.step_name == "Complete"

    def test_to_dict_serialization(self) -> None:
        """State serializes to a dict with all required fields."""
        state = PovGenerationState(
            engagement_id="eng-001",
            pov_id="pov-001",
            version=2,
            status="COMPLETED",
        )

        data = state.to_dict()
        assert data["engagement_id"] == "eng-001"
        assert data["pov_id"] == "pov-001"
        assert data["version"] == 2
        assert data["status"] == "COMPLETED"
        assert "completed_steps" in data
        assert "partial_data" in data


# --- Consensus step info tests -----------------------------------------------


class TestConsensusStepInfo:
    """get_step_info utility."""

    def test_valid_step_numbers(self) -> None:
        """All 8 step numbers return valid info."""
        for i in range(1, 9):
            info = get_step_info(i)
            assert "name" in info
            assert "number" in info

    def test_step_1_is_evidence_aggregation(self) -> None:
        """Step 1 is Evidence Aggregation."""
        info = get_step_info(1)
        assert info["name"] == "Evidence Aggregation"

    def test_step_8_is_gap_detection(self) -> None:
        """Step 8 is Gap Detection."""
        info = get_step_info(8)
        assert info["name"] == "Gap Detection"

    def test_invalid_step_zero(self) -> None:
        """Step 0 raises ValueError."""
        with pytest.raises(ValueError, match="between 1 and 8"):
            get_step_info(0)

    def test_invalid_step_nine(self) -> None:
        """Step 9 raises ValueError."""
        with pytest.raises(ValueError, match="between 1 and 8"):
            get_step_info(9)

    def test_total_steps_constant(self) -> None:
        """TOTAL_STEPS is 8."""
        assert TOTAL_STEPS == 8
        assert len(POV_STEPS) == 8
