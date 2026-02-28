"""BDD tests for the scenario simulation adapter (Story #380).

Scenario 1: Cycle time estimation for task removals
Scenario 2: Staffing impact from role reassignments
Scenario 3: Async simulation (adapter-level)
Scenario 4: Confidence overlay on modified elements
"""

from __future__ import annotations

from src.core.models.simulation import ModificationType
from src.core.services.scenario_simulation import (
    ElementImpact,
    ScenarioSimulationAdapter,
    SimulationOutput,
    apply_confidence_overlay,
)


class TestCycleTimeTaskRemoval:
    """Scenario 1: Cycle time estimation for task removals."""

    def test_3_task_removals_reduce_cycle_time(self) -> None:
        """Given a scenario with 3 task removal modifications,
        When simulation is run,
        Then cycle time delta reflects the total removed task hours."""
        adapter = ScenarioSimulationAdapter(
            baseline_cycle_time_hrs=100.0,
            task_durations={"t1": 10.0, "t2": 20.0, "t3": 5.0},
        )
        modifications = [
            {"modification_type": ModificationType.TASK_REMOVE, "element_id": "t1", "element_name": "Task 1"},
            {"modification_type": ModificationType.TASK_REMOVE, "element_id": "t2", "element_name": "Task 2"},
            {"modification_type": ModificationType.TASK_REMOVE, "element_id": "t3", "element_name": "Task 3"},
        ]
        output = adapter.simulate(modifications)

        # 100 - (10+20+5) = 65 -> delta = 35%
        assert output.modified_cycle_time_hrs == 65.0
        assert abs(output.cycle_time_delta_pct - 35.0) < 0.01

    def test_task_removal_uses_default_duration(self) -> None:
        """When no task_durations mapping exists, use default (4.0 hrs)."""
        adapter = ScenarioSimulationAdapter(baseline_cycle_time_hrs=50.0)
        modifications = [
            {
                "modification_type": ModificationType.TASK_REMOVE,
                "element_id": "unknown",
                "element_name": "Unknown Task",
            },
        ]
        output = adapter.simulate(modifications)

        # 50 - 4 = 46 -> delta = 8%
        assert output.modified_cycle_time_hrs == 46.0
        assert abs(output.cycle_time_delta_pct - 8.0) < 0.01

    def test_task_removal_with_estimated_hours_in_change_data(self) -> None:
        """When change_data provides estimated_hours, use that instead of default."""
        adapter = ScenarioSimulationAdapter(baseline_cycle_time_hrs=100.0)
        modifications = [
            {
                "modification_type": ModificationType.TASK_REMOVE,
                "element_id": "t1",
                "element_name": "Task 1",
                "change_data": {"estimated_hours": 15.0},
            },
        ]
        output = adapter.simulate(modifications)

        assert output.modified_cycle_time_hrs == 85.0

    def test_removal_does_not_go_below_zero(self) -> None:
        """Cycle time cannot go negative even with massive removals."""
        adapter = ScenarioSimulationAdapter(
            baseline_cycle_time_hrs=10.0,
            task_durations={"t1": 50.0, "t2": 50.0},
        )
        modifications = [
            {"modification_type": ModificationType.TASK_REMOVE, "element_id": "t1", "element_name": "T1"},
            {"modification_type": ModificationType.TASK_REMOVE, "element_id": "t2", "element_name": "T2"},
        ]
        output = adapter.simulate(modifications)

        assert output.modified_cycle_time_hrs == 0.0
        assert output.cycle_time_delta_pct == 100.0


class TestStaffingImpact:
    """Scenario 2: Staffing impact from role reassignments."""

    def test_human_to_system_reduces_fte(self) -> None:
        """Given 2 role reassignments from human to system,
        When simulation completes,
        Then FTE delta is -2.0."""
        adapter = ScenarioSimulationAdapter(fte_per_activity=1.0)
        modifications = [
            {
                "modification_type": ModificationType.ROLE_REASSIGN,
                "element_id": "a1",
                "element_name": "Activity 1",
                "change_data": {"from_role": "analyst", "to_role": "rpa_bot"},
            },
            {
                "modification_type": ModificationType.ROLE_REASSIGN,
                "element_id": "a2",
                "element_name": "Activity 2",
                "change_data": {"from_role": "manager", "to_role": "automated_system"},
            },
        ]
        output = adapter.simulate(modifications)

        assert output.total_fte_delta == -2.0

    def test_system_to_human_increases_fte(self) -> None:
        """Reassigning from system to human increases FTE."""
        adapter = ScenarioSimulationAdapter(fte_per_activity=1.0)
        modifications = [
            {
                "modification_type": ModificationType.ROLE_REASSIGN,
                "element_id": "a1",
                "element_name": "Activity 1",
                "change_data": {"from_role": "bot", "to_role": "analyst"},
            },
        ]
        output = adapter.simulate(modifications)

        assert output.total_fte_delta == 1.0

    def test_human_to_human_no_fte_change(self) -> None:
        """Reassigning between humans has no FTE impact."""
        adapter = ScenarioSimulationAdapter(fte_per_activity=1.0)
        modifications = [
            {
                "modification_type": ModificationType.ROLE_REASSIGN,
                "element_id": "a1",
                "element_name": "Activity 1",
                "change_data": {"from_role": "analyst", "to_role": "senior_analyst"},
            },
        ]
        output = adapter.simulate(modifications)

        assert output.total_fte_delta == 0.0

    def test_per_element_fte_delta(self) -> None:
        """Each element reports its own FTE delta."""
        adapter = ScenarioSimulationAdapter(fte_per_activity=1.0)
        modifications = [
            {
                "modification_type": ModificationType.ROLE_REASSIGN,
                "element_id": "a1",
                "element_name": "Activity 1",
                "change_data": {"from_role": "clerk", "to_role": "api_system"},
            },
        ]
        output = adapter.simulate(modifications)

        assert len(output.per_element_results) == 1
        assert output.per_element_results[0].fte_delta == -1.0


class TestTaskAddAndModify:
    """Task additions and modifications affect cycle time."""

    def test_task_add_increases_cycle_time(self) -> None:
        """Adding a task increases cycle time."""
        adapter = ScenarioSimulationAdapter(baseline_cycle_time_hrs=100.0)
        modifications = [
            {
                "modification_type": ModificationType.TASK_ADD,
                "element_id": "new1",
                "element_name": "New Review",
                "change_data": {"estimated_hours": 8.0},
            },
        ]
        output = adapter.simulate(modifications)

        assert output.modified_cycle_time_hrs == 108.0
        assert output.per_element_results[0].confidence_classification == "DARK"

    def test_task_modify_applies_delta(self) -> None:
        """Modifying a task applies cycle_time_delta_hrs."""
        adapter = ScenarioSimulationAdapter(baseline_cycle_time_hrs=100.0)
        modifications = [
            {
                "modification_type": ModificationType.TASK_MODIFY,
                "element_id": "t1",
                "element_name": "Task 1",
                "change_data": {"cycle_time_delta_hrs": -3.5},
            },
        ]
        output = adapter.simulate(modifications)

        assert output.modified_cycle_time_hrs == 96.5


class TestGatewayAndControlModifications:
    """Gateway restructure and control add/remove."""

    def test_gateway_restructure_is_dark(self) -> None:
        """Gateway restructure is classified as DARK due to structural uncertainty."""
        adapter = ScenarioSimulationAdapter(baseline_cycle_time_hrs=100.0)
        modifications = [
            {
                "modification_type": ModificationType.GATEWAY_RESTRUCTURE,
                "element_id": "g1",
                "element_name": "Approval Gateway",
                "change_data": {"cycle_time_delta_hrs": -5.0},
            },
        ]
        output = adapter.simulate(modifications)

        assert output.modified_cycle_time_hrs == 95.0
        assert output.per_element_results[0].confidence_classification == "DARK"

    def test_control_add_is_dim(self) -> None:
        """Adding a control is DIM confidence."""
        adapter = ScenarioSimulationAdapter(baseline_cycle_time_hrs=100.0)
        modifications = [
            {
                "modification_type": ModificationType.CONTROL_ADD,
                "element_id": "c1",
                "element_name": "SOX Control",
                "change_data": {"cycle_time_delta_hrs": 2.0},
            },
        ]
        output = adapter.simulate(modifications)

        assert output.modified_cycle_time_hrs == 102.0
        assert output.per_element_results[0].confidence_classification == "DIM"

    def test_control_remove_is_dark(self) -> None:
        """Removing a control is DARK confidence."""
        adapter = ScenarioSimulationAdapter(baseline_cycle_time_hrs=100.0)
        modifications = [
            {
                "modification_type": ModificationType.CONTROL_REMOVE,
                "element_id": "c1",
                "element_name": "Redundant Check",
                "change_data": {"cycle_time_delta_hrs": -1.0},
            },
        ]
        output = adapter.simulate(modifications)

        assert output.modified_cycle_time_hrs == 99.0
        assert output.per_element_results[0].confidence_classification == "DARK"


class TestConfidenceOverlay:
    """Scenario 4: Confidence overlay on modified elements."""

    def test_removing_bright_element_becomes_dark(self) -> None:
        """Removing a well-evidenced (BRIGHT) element reduces scenario confidence to DARK."""
        impacts = [
            ElementImpact(
                element_id="t1",
                element_name="Task 1",
                modification_type=ModificationType.TASK_REMOVE,
                cycle_time_delta_hrs=-10.0,
                fte_delta=0.0,
                confidence_classification="DIM",
            ),
        ]
        existing = {"t1": "BRIGHT"}
        overlay = apply_confidence_overlay(impacts, existing)

        assert len(overlay) == 1
        assert overlay[0]["original_classification"] == "BRIGHT"
        assert overlay[0]["modified_classification"] == "DARK"
        assert overlay[0]["confidence_changed"] is True

    def test_removing_dim_element_stays_dim(self) -> None:
        """Removing a DIM element stays DIM (no downgrade)."""
        impacts = [
            ElementImpact(
                element_id="t1",
                element_name="Task 1",
                modification_type=ModificationType.TASK_REMOVE,
                cycle_time_delta_hrs=-5.0,
                fte_delta=0.0,
                confidence_classification="DIM",
            ),
        ]
        existing = {"t1": "DIM"}
        overlay = apply_confidence_overlay(impacts, existing)

        assert overlay[0]["original_classification"] == "DIM"
        assert overlay[0]["modified_classification"] == "DIM"
        assert overlay[0]["confidence_changed"] is False

    def test_new_task_always_dark(self) -> None:
        """New tasks have no evidence and are classified DARK."""
        impacts = [
            ElementImpact(
                element_id="new1",
                element_name="New Task",
                modification_type=ModificationType.TASK_ADD,
                cycle_time_delta_hrs=5.0,
                fte_delta=0.0,
                confidence_classification="DARK",
            ),
        ]
        overlay = apply_confidence_overlay(impacts, {})

        assert overlay[0]["modified_classification"] == "DARK"

    def test_overlay_reports_change_status(self) -> None:
        """Each overlay entry reports whether classification changed."""
        impacts = [
            ElementImpact(
                element_id="t1",
                element_name="Task 1",
                modification_type=ModificationType.ROLE_REASSIGN,
                cycle_time_delta_hrs=0.0,
                fte_delta=-1.0,
                confidence_classification="DIM",
            ),
        ]
        # If original was BRIGHT and now DIM, it changed
        overlay = apply_confidence_overlay(impacts, {"t1": "BRIGHT"})

        assert overlay[0]["confidence_changed"] is True
        assert overlay[0]["original_classification"] == "BRIGHT"
        assert overlay[0]["modified_classification"] == "DIM"

    def test_unknown_element_defaults_dim(self) -> None:
        """Elements not in existing_confidence default to DIM."""
        impacts = [
            ElementImpact(
                element_id="unknown",
                element_name="Unknown",
                modification_type=ModificationType.TASK_MODIFY,
                cycle_time_delta_hrs=0.0,
                fte_delta=0.0,
                confidence_classification="DIM",
            ),
        ]
        overlay = apply_confidence_overlay(impacts, {})

        assert overlay[0]["original_classification"] == "DIM"
        assert overlay[0]["modified_classification"] == "DIM"
        assert overlay[0]["confidence_changed"] is False


class TestSimulationOutputSerialization:
    """Output objects serialize correctly."""

    def test_element_impact_to_dict(self) -> None:
        impact = ElementImpact(
            element_id="t1",
            element_name="Task 1",
            modification_type="task_remove",
            cycle_time_delta_hrs=-10.123,
            fte_delta=-1.567,
            confidence_classification="DARK",
        )
        d = impact.to_dict()
        assert d["cycle_time_delta_hrs"] == -10.12
        assert d["fte_delta"] == -1.57

    def test_simulation_output_to_dict(self) -> None:
        output = SimulationOutput(
            cycle_time_delta_pct=35.456,
            total_fte_delta=-2.789,
            per_element_results=[],
            execution_time_ms=42,
            baseline_cycle_time_hrs=100.0,
            modified_cycle_time_hrs=64.544,
        )
        d = output.to_dict()
        assert d["cycle_time_delta_pct"] == 35.46
        assert d["total_fte_delta"] == -2.79
        assert d["modified_cycle_time_hrs"] == 64.54
        assert d["execution_time_ms"] == 42


class TestEmptyAndEdgeCases:
    """Edge cases for simulation adapter."""

    def test_empty_modifications(self) -> None:
        """No modifications means no change."""
        adapter = ScenarioSimulationAdapter(baseline_cycle_time_hrs=100.0)
        output = adapter.simulate([])

        assert output.cycle_time_delta_pct == 0.0
        assert output.total_fte_delta == 0.0
        assert output.modified_cycle_time_hrs == 100.0
        assert output.per_element_results == []

    def test_zero_baseline(self) -> None:
        """Zero baseline cycle time produces zero delta percentage."""
        adapter = ScenarioSimulationAdapter(baseline_cycle_time_hrs=0.0)
        modifications = [
            {
                "modification_type": ModificationType.TASK_ADD,
                "element_id": "t1",
                "element_name": "Task",
                "change_data": {"estimated_hours": 5.0},
            },
        ]
        output = adapter.simulate(modifications)

        assert output.cycle_time_delta_pct == 0.0
        assert output.modified_cycle_time_hrs == 5.0

    def test_execution_time_is_nonnegative(self) -> None:
        """Execution time should always be >= 0."""
        adapter = ScenarioSimulationAdapter()
        output = adapter.simulate([])
        assert output.execution_time_ms >= 0

    def test_mixed_modifications(self) -> None:
        """Mixed modification types produce correct aggregate results."""
        adapter = ScenarioSimulationAdapter(
            baseline_cycle_time_hrs=100.0,
            task_durations={"t1": 10.0},
            fte_per_activity=1.0,
        )
        modifications = [
            {"modification_type": ModificationType.TASK_REMOVE, "element_id": "t1", "element_name": "Remove"},
            {
                "modification_type": ModificationType.TASK_ADD,
                "element_id": "t2",
                "element_name": "Add",
                "change_data": {"estimated_hours": 5.0},
            },
            {
                "modification_type": ModificationType.ROLE_REASSIGN,
                "element_id": "a1",
                "element_name": "Reassign",
                "change_data": {"from_role": "clerk", "to_role": "rpa_bot"},
            },
        ]
        output = adapter.simulate(modifications)

        # Cycle: 100 - 10 + 5 = 95
        assert output.modified_cycle_time_hrs == 95.0
        # FTE: -1.0 from reassignment
        assert output.total_fte_delta == -1.0
        assert len(output.per_element_results) == 3
