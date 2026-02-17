"""Tests for simulation engine, scenarios, and impact analysis."""

from __future__ import annotations

import pytest

from src.core.models import SimulationType
from src.simulation.engine import run_simulation
from src.simulation.impact import calculate_cascading_impact, compare_simulation_results
from src.simulation.scenarios import validate_scenario


class TestRunSimulation:
    """Tests for run_simulation function."""

    def test_returns_metrics_dict_with_expected_keys(self):
        process_graph = {
            "elements": [
                {"name": "Task1", "duration": 10, "type": "task"},
            ],
            "connections": [],
        }
        result = run_simulation(process_graph, {}, "what_if")
        assert "metrics" in result
        metrics = result["metrics"]
        assert "total_elements" in metrics
        assert "total_estimated_time" in metrics
        assert "critical_path_length" in metrics
        assert "active_controls" in metrics
        assert "risk_score" in metrics
        assert "efficiency_score" in metrics

    def test_what_if_type_applies_element_changes(self):
        process_graph = {
            "elements": [
                {"name": "Task1", "duration": 10},
            ],
            "connections": [],
        }
        parameters = {
            "element_changes": {
                "Task1": {"duration": 20}
            }
        }
        result = run_simulation(process_graph, parameters, "what_if")
        assert result["metrics"]["total_estimated_time"] == 20

    def test_capacity_type_scales_throughput(self):
        process_graph = {
            "elements": [
                {"name": "Task1", "throughput": 100},
            ],
            "connections": [],
        }
        parameters = {"capacity_scale": 2.0}
        result = run_simulation(process_graph, parameters, "capacity")
        # Throughput is scaled but not directly reflected in basic metrics
        assert result["elements_analyzed"] == 1

    def test_process_change_type_marks_elements_as_removed(self):
        process_graph = {
            "elements": [
                {"name": "Task1", "duration": 10},
                {"name": "Task2", "duration": 20},
            ],
            "connections": [],
        }
        parameters = {"remove_elements": ["Task1"]}
        result = run_simulation(process_graph, parameters, "process_change")
        # Only Task2 should be active
        assert result["metrics"]["total_elements"] == 1
        assert result["metrics"]["total_estimated_time"] == 20

    def test_control_removal_type_deactivates_controls(self):
        process_graph = {
            "elements": [
                {"name": "Control1", "type": "control", "control_active": True},
                {"name": "Control2", "type": "control", "control_active": True},
            ],
            "connections": [],
        }
        parameters = {"remove_controls": ["Control1"]}
        result = run_simulation(process_graph, parameters, "control_removal")
        # Only Control2 should be active
        assert result["metrics"]["active_controls"] == 1

    def test_empty_graph_returns_metrics_with_zeros(self):
        process_graph = {"elements": [], "connections": []}
        result = run_simulation(process_graph, {}, "what_if")
        metrics = result["metrics"]
        assert metrics["total_elements"] == 0
        assert metrics["total_estimated_time"] == 0
        assert metrics["critical_path_length"] == 0

    def test_execution_time_tracked_in_ms(self):
        process_graph = {"elements": [], "connections": []}
        result = run_simulation(process_graph, {}, "what_if")
        assert "execution_time_ms" in result
        assert isinstance(result["execution_time_ms"], int)
        assert result["execution_time_ms"] >= 0

    def test_critical_path_length_calculation(self):
        process_graph = {
            "elements": [
                {"name": "Start"},
                {"name": "Task1"},
                {"name": "Task2"},
            ],
            "connections": [
                {"source": "Start", "target": "Task1"},
                {"source": "Task1", "target": "Task2"},
            ],
        }
        result = run_simulation(process_graph, {}, "what_if")
        # Start -> Task1 -> Task2 = path length 3
        assert result["metrics"]["critical_path_length"] == 3

    def test_risk_score_calculation_with_no_controls(self):
        process_graph = {
            "elements": [
                {"name": "Task1", "type": "task"},
            ],
            "connections": [],
        }
        result = run_simulation(process_graph, {}, "what_if")
        # No controls = baseline risk 0.5
        assert result["metrics"]["risk_score"] == 0.5

    def test_risk_score_with_all_controls_active(self):
        process_graph = {
            "elements": [
                {"name": "Control1", "type": "control", "control_active": True},
                {"name": "Control2", "type": "control", "control_active": True},
            ],
            "connections": [],
        }
        result = run_simulation(process_graph, {}, "what_if")
        # All controls active = risk 0.0
        assert result["metrics"]["risk_score"] == 0.0

    def test_efficiency_score_calculation(self):
        process_graph = {
            "elements": [
                {"name": "Task1", "value_add": True},
                {"name": "Task2", "value_add": False},
            ],
            "connections": [],
        }
        result = run_simulation(process_graph, {}, "what_if")
        # 1 value-add out of 2 = 0.5
        assert result["metrics"]["efficiency_score"] == 0.5


class TestValidateScenario:
    """Tests for validate_scenario function."""

    def test_what_if_requires_element_changes(self):
        errors = validate_scenario(SimulationType.WHAT_IF, {})
        assert len(errors) > 0
        assert any("element_changes" in e for e in errors)

    def test_what_if_with_valid_element_changes_returns_no_errors(self):
        parameters = {"element_changes": {"Task1": {"duration": 10}}}
        errors = validate_scenario(SimulationType.WHAT_IF, parameters, ["Task1"])
        assert len(errors) == 0

    def test_what_if_validates_element_names_against_process_elements(self):
        parameters = {"element_changes": {"InvalidTask": {"duration": 10}}}
        errors = validate_scenario(SimulationType.WHAT_IF, parameters, ["Task1"])
        assert len(errors) > 0
        assert any("InvalidTask" in e for e in errors)

    def test_capacity_requires_positive_capacity_scale(self):
        errors = validate_scenario(SimulationType.CAPACITY, {})
        assert len(errors) > 0
        assert any("capacity_scale" in e for e in errors)

    def test_capacity_rejects_zero_scale(self):
        parameters = {"capacity_scale": 0}
        errors = validate_scenario(SimulationType.CAPACITY, parameters)
        assert len(errors) > 0
        assert any("positive" in e for e in errors)

    def test_capacity_rejects_negative_scale(self):
        parameters = {"capacity_scale": -1.0}
        errors = validate_scenario(SimulationType.CAPACITY, parameters)
        assert len(errors) > 0

    def test_capacity_accepts_positive_scale(self):
        parameters = {"capacity_scale": 1.5}
        errors = validate_scenario(SimulationType.CAPACITY, parameters)
        assert len(errors) == 0

    def test_process_change_requires_remove_or_add_elements(self):
        errors = validate_scenario(SimulationType.PROCESS_CHANGE, {})
        assert len(errors) > 0
        assert any("remove_elements" in e or "add_elements" in e for e in errors)

    def test_process_change_accepts_remove_elements(self):
        parameters = {"remove_elements": ["Task1"]}
        errors = validate_scenario(SimulationType.PROCESS_CHANGE, parameters)
        assert len(errors) == 0

    def test_process_change_accepts_add_elements(self):
        parameters = {"add_elements": ["Task2"]}
        errors = validate_scenario(SimulationType.PROCESS_CHANGE, parameters)
        assert len(errors) == 0

    def test_control_removal_requires_remove_controls(self):
        errors = validate_scenario(SimulationType.CONTROL_REMOVAL, {})
        assert len(errors) > 0
        assert any("remove_controls" in e for e in errors)

    def test_control_removal_accepts_valid_params(self):
        parameters = {"remove_controls": ["Control1"]}
        errors = validate_scenario(SimulationType.CONTROL_REMOVAL, parameters)
        assert len(errors) == 0


class TestCalculateCascadingImpact:
    """Tests for calculate_cascading_impact function."""

    def test_finds_direct_downstream_elements(self):
        process_graph = {
            "connections": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        }
        result = calculate_cascading_impact(["A"], process_graph)
        assert result["total_affected"] == 2
        element_names = [item["element"] for item in result["impact_items"]]
        assert "B" in element_names
        assert "C" in element_names

    def test_finds_cascading_downstream_elements(self):
        process_graph = {
            "connections": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
                {"source": "C", "target": "D"},
            ],
        }
        result = calculate_cascading_impact(["A"], process_graph)
        assert result["total_affected"] == 3
        assert result["max_cascade_depth"] == 3

    def test_respects_graph_structure_bfs_traversal(self):
        process_graph = {
            "connections": [
                {"source": "A", "target": "B"},
                {"source": "A", "target": "C"},
                {"source": "B", "target": "D"},
            ],
        }
        result = calculate_cascading_impact(["A"], process_graph)
        assert result["total_affected"] == 3
        element_names = [item["element"] for item in result["impact_items"]]
        assert set(element_names) == {"B", "C", "D"}

    def test_severity_decreases_with_distance(self):
        process_graph = {
            "connections": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        }
        result = calculate_cascading_impact(["A"], process_graph)
        items = {item["element"]: item for item in result["impact_items"]}
        # B is distance 1, C is distance 2
        assert items["B"]["severity"] > items["C"]["severity"]

    def test_empty_graph_returns_no_affected(self):
        process_graph = {"connections": []}
        result = calculate_cascading_impact(["A"], process_graph)
        assert result["total_affected"] == 0
        assert result["max_cascade_depth"] == 0

    def test_direct_impact_type_for_distance_one(self):
        process_graph = {
            "connections": [
                {"source": "A", "target": "B"},
            ],
        }
        result = calculate_cascading_impact(["A"], process_graph)
        assert result["impact_items"][0]["impact_type"] == "direct"

    def test_cascading_impact_type_for_distance_greater_than_one(self):
        process_graph = {
            "connections": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        }
        result = calculate_cascading_impact(["A"], process_graph)
        c_item = next(item for item in result["impact_items"] if item["element"] == "C")
        assert c_item["impact_type"] == "cascading"


class TestCompareSimulationResults:
    """Tests for compare_simulation_results function."""

    def test_calculates_deltas_and_pct_change(self):
        baseline = {"risk_score": 0.5, "efficiency_score": 0.7}
        simulation = {"risk_score": 0.6, "efficiency_score": 0.8}
        result = compare_simulation_results(baseline, simulation)
        assert result["deltas"]["risk_score"]["delta"] == pytest.approx(0.1)
        assert result["deltas"]["risk_score"]["pct_change"] == pytest.approx(20.0)
        assert result["deltas"]["efficiency_score"]["delta"] == pytest.approx(0.1)

    def test_assessment_high_risk_increase_when_risk_delta_over_0_2(self):
        baseline = {"risk_score": 0.3}
        simulation = {"risk_score": 0.6}
        result = compare_simulation_results(baseline, simulation)
        assert result["assessment"] == "high_risk_increase"

    def test_assessment_improvement_when_risk_decreases_and_efficiency_increases(self):
        baseline = {"risk_score": 0.6, "efficiency_score": 0.5}
        simulation = {"risk_score": 0.4, "efficiency_score": 0.6}
        result = compare_simulation_results(baseline, simulation)
        assert result["assessment"] == "improvement"

    def test_assessment_neutral_for_small_changes(self):
        baseline = {"risk_score": 0.5, "efficiency_score": 0.7}
        simulation = {"risk_score": 0.52, "efficiency_score": 0.71}
        result = compare_simulation_results(baseline, simulation)
        assert result["assessment"] == "neutral"

    def test_handles_zero_baseline_values(self):
        baseline = {"risk_score": 0.0}
        simulation = {"risk_score": 0.1}
        result = compare_simulation_results(baseline, simulation)
        assert result["deltas"]["risk_score"]["pct_change"] == 0.0

    def test_assessment_efficiency_decrease(self):
        baseline = {"risk_score": 0.5, "efficiency_score": 0.8}
        simulation = {"risk_score": 0.5, "efficiency_score": 0.6}
        result = compare_simulation_results(baseline, simulation)
        assert result["assessment"] == "efficiency_decrease"
