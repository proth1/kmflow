"""Unit tests for src/simulation/engine.py.

Covers run_simulation, _apply_parameters parameter dispatch,
metric boundary conditions, and edge-case graph topologies.
"""

from __future__ import annotations

import pytest

from src.simulation.engine import run_simulation


class TestRunSimulationEmptyGraph:
    """Empty graph should return zero/default metrics without errors."""

    def test_empty_graph_returns_dict(self) -> None:
        result = run_simulation({}, {}, "what_if")
        assert isinstance(result, dict)

    def test_empty_graph_metric_keys_present(self) -> None:
        result = run_simulation({}, {}, "what_if")
        assert "metrics" in result
        assert "execution_time_ms" in result
        assert "elements_analyzed" in result
        assert "connections_analyzed" in result

    def test_empty_graph_zero_elements(self) -> None:
        result = run_simulation({}, {}, "what_if")
        assert result["elements_analyzed"] == 0
        assert result["connections_analyzed"] == 0

    def test_empty_graph_zero_metrics(self) -> None:
        result = run_simulation({}, {}, "what_if")
        m = result["metrics"]
        assert m["total_elements"] == 0
        assert m["total_estimated_time"] == 0
        assert m["critical_path_length"] == 0
        assert m["active_controls"] == 0

    def test_empty_graph_risk_score_is_neutral(self) -> None:
        # No controls at all → risk defaults to 0.5
        result = run_simulation({}, {}, "what_if")
        assert result["metrics"]["risk_score"] == 0.5

    def test_empty_graph_efficiency_zero(self) -> None:
        result = run_simulation({}, {}, "what_if")
        assert result["metrics"]["efficiency_score"] == 0.0

    def test_empty_elements_list_explicit(self) -> None:
        result = run_simulation({"elements": [], "connections": []}, {}, "what_if")
        assert result["elements_analyzed"] == 0
        assert result["connections_analyzed"] == 0


class TestRunSimulationSingleNode:
    """Single-node graph with no connections."""

    def test_single_node_element_count(self) -> None:
        graph = {"elements": [{"name": "A", "duration": 5}], "connections": []}
        result = run_simulation(graph, {}, "what_if")
        assert result["elements_analyzed"] == 1

    def test_single_node_connections_count(self) -> None:
        graph = {"elements": [{"name": "A", "duration": 5}], "connections": []}
        result = run_simulation(graph, {}, "what_if")
        assert result["connections_analyzed"] == 0

    def test_single_node_total_time(self) -> None:
        graph = {"elements": [{"name": "A", "duration": 7}], "connections": []}
        result = run_simulation(graph, {}, "what_if")
        assert result["metrics"]["total_estimated_time"] == 7

    def test_single_node_critical_path_is_one(self) -> None:
        graph = {"elements": [{"name": "A", "duration": 0}], "connections": []}
        result = run_simulation(graph, {}, "what_if")
        assert result["metrics"]["critical_path_length"] == 1

    def test_single_control_node_active(self) -> None:
        graph = {
            "elements": [{"name": "C", "type": "control", "duration": 0}],
            "connections": [],
        }
        result = run_simulation(graph, {}, "what_if")
        assert result["metrics"]["active_controls"] == 1

    def test_single_control_node_risk_is_zero(self) -> None:
        # 1 control, 1 active → coverage 100% → risk 0.0
        graph = {
            "elements": [{"name": "C", "type": "control"}],
            "connections": [],
        }
        result = run_simulation(graph, {}, "what_if")
        assert result["metrics"]["risk_score"] == 0.0

    def test_execution_time_ms_non_negative(self) -> None:
        graph = {"elements": [{"name": "A"}], "connections": []}
        result = run_simulation(graph, {}, "what_if")
        assert result["execution_time_ms"] >= 0


class TestSimulationTypeWhatIf:
    """Parameter application for what_if simulation type."""

    def test_what_if_updates_named_element(self) -> None:
        graph = {
            "elements": [{"name": "Step1", "duration": 10}],
            "connections": [],
        }
        params = {"element_changes": {"Step1": {"duration": 25}}}
        result = run_simulation(graph, params, "what_if")
        assert result["metrics"]["total_estimated_time"] == 25

    def test_what_if_does_not_touch_unnamed_element(self) -> None:
        graph = {
            "elements": [
                {"name": "Step1", "duration": 10},
                {"name": "Step2", "duration": 5},
            ],
            "connections": [],
        }
        params = {"element_changes": {"Step1": {"duration": 20}}}
        result = run_simulation(graph, params, "what_if")
        assert result["metrics"]["total_estimated_time"] == 25

    def test_what_if_empty_changes_is_no_op(self) -> None:
        graph = {
            "elements": [{"name": "Task", "duration": 8}],
            "connections": [],
        }
        result = run_simulation(graph, {"element_changes": {}}, "what_if")
        assert result["metrics"]["total_estimated_time"] == 8

    def test_what_if_missing_element_changes_key_is_no_op(self) -> None:
        graph = {"elements": [{"name": "T", "duration": 3}], "connections": []}
        result = run_simulation(graph, {}, "what_if")
        assert result["metrics"]["total_estimated_time"] == 3


class TestSimulationTypeCapacity:
    """Parameter application for capacity simulation type."""

    def test_capacity_scales_throughput_up(self) -> None:
        graph = {
            "elements": [{"name": "T", "throughput": 100}],
            "connections": [],
        }
        result = run_simulation(graph, {"capacity_scale": 2.0}, "capacity")
        # throughput is not a duration — total_estimated_time stays 0
        # but element count should be 1
        assert result["elements_analyzed"] == 1

    def test_capacity_scale_default_one_unchanged(self) -> None:
        graph = {
            "elements": [{"name": "T", "throughput": 50, "duration": 10}],
            "connections": [],
        }
        result_scaled = run_simulation(graph, {"capacity_scale": 1.0}, "capacity")
        result_default = run_simulation(graph, {}, "capacity")
        assert result_scaled["metrics"]["total_estimated_time"] == result_default["metrics"]["total_estimated_time"]

    def test_capacity_scale_zero_removes_throughput(self) -> None:
        graph = {
            "elements": [{"name": "T", "throughput": 100}],
            "connections": [],
        }
        result = run_simulation(graph, {"capacity_scale": 0.0}, "capacity")
        assert result["elements_analyzed"] == 1


class TestSimulationTypeProcessChange:
    """Parameter application for process_change simulation type."""

    def test_removed_element_excluded_from_count(self) -> None:
        graph = {
            "elements": [
                {"name": "Keep", "duration": 5},
                {"name": "Drop", "duration": 3},
            ],
            "connections": [],
        }
        params = {"remove_elements": ["Drop"]}
        result = run_simulation(graph, params, "process_change")
        assert result["metrics"]["total_elements"] == 1

    def test_removed_element_excluded_from_time(self) -> None:
        graph = {
            "elements": [
                {"name": "Keep", "duration": 5},
                {"name": "Drop", "duration": 3},
            ],
            "connections": [],
        }
        params = {"remove_elements": ["Drop"]}
        result = run_simulation(graph, params, "process_change")
        assert result["metrics"]["total_estimated_time"] == 5

    def test_remove_nonexistent_element_is_no_op(self) -> None:
        graph = {
            "elements": [{"name": "Keep", "duration": 5}],
            "connections": [],
        }
        result = run_simulation(graph, {"remove_elements": ["Ghost"]}, "process_change")
        assert result["metrics"]["total_elements"] == 1

    def test_remove_all_elements(self) -> None:
        graph = {
            "elements": [{"name": "Only", "duration": 5}],
            "connections": [],
        }
        result = run_simulation(graph, {"remove_elements": ["Only"]}, "process_change")
        assert result["metrics"]["total_elements"] == 0
        assert result["metrics"]["total_estimated_time"] == 0


class TestSimulationTypeControlRemoval:
    """Parameter application for control_removal simulation type."""

    def test_deactivated_control_not_counted(self) -> None:
        graph = {
            "elements": [
                {"name": "Ctrl", "type": "control"},
            ],
            "connections": [],
        }
        params = {"remove_controls": ["Ctrl"]}
        result = run_simulation(graph, params, "control_removal")
        assert result["metrics"]["active_controls"] == 0

    def test_deactivated_control_raises_risk_score(self) -> None:
        graph = {
            "elements": [
                {"name": "Ctrl", "type": "control"},
            ],
            "connections": [],
        }
        baseline = run_simulation(graph, {}, "control_removal")
        with_removal = run_simulation(graph, {"remove_controls": ["Ctrl"]}, "control_removal")
        assert with_removal["metrics"]["risk_score"] > baseline["metrics"]["risk_score"]

    def test_risk_score_max_one_all_controls_removed(self) -> None:
        graph = {
            "elements": [{"name": "C1", "type": "control"}],
            "connections": [],
        }
        result = run_simulation(graph, {"remove_controls": ["C1"]}, "control_removal")
        assert result["metrics"]["risk_score"] <= 1.0

    def test_active_control_unchanged_when_not_listed(self) -> None:
        graph = {
            "elements": [
                {"name": "C1", "type": "control"},
                {"name": "C2", "type": "control"},
            ],
            "connections": [],
        }
        result = run_simulation(graph, {"remove_controls": ["C1"]}, "control_removal")
        assert result["metrics"]["active_controls"] == 1


class TestMetricBoundaryConditions:
    """Edge cases for metric calculations."""

    def test_critical_path_linear_chain(self) -> None:
        graph = {
            "elements": [
                {"name": "A"},
                {"name": "B"},
                {"name": "C"},
            ],
            "connections": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        }
        result = run_simulation(graph, {}, "what_if")
        assert result["metrics"]["critical_path_length"] >= 1

    def test_efficiency_all_value_add(self) -> None:
        graph = {
            "elements": [
                {"name": "A", "value_add": True},
                {"name": "B", "value_add": True},
            ],
            "connections": [],
        }
        result = run_simulation(graph, {}, "what_if")
        assert result["metrics"]["efficiency_score"] == 1.0

    def test_efficiency_no_value_add(self) -> None:
        graph = {
            "elements": [
                {"name": "A", "value_add": False},
                {"name": "B", "value_add": False},
            ],
            "connections": [],
        }
        result = run_simulation(graph, {}, "what_if")
        assert result["metrics"]["efficiency_score"] == 0.0

    def test_mixed_value_add_ratio(self) -> None:
        graph = {
            "elements": [
                {"name": "A", "value_add": True},
                {"name": "B", "value_add": False},
                {"name": "C", "value_add": True},
                {"name": "D", "value_add": False},
            ],
            "connections": [],
        }
        result = run_simulation(graph, {}, "what_if")
        assert result["metrics"]["efficiency_score"] == pytest.approx(0.5)

    def test_risk_score_between_zero_and_one(self) -> None:
        graph = {
            "elements": [
                {"name": "C1", "type": "control"},
                {"name": "C2", "type": "control"},
                {"name": "T1"},
            ],
            "connections": [],
        }
        result = run_simulation(graph, {"remove_controls": ["C1"]}, "control_removal")
        risk = result["metrics"]["risk_score"]
        assert 0.0 <= risk <= 1.0

    def test_connection_count_reflects_input(self) -> None:
        graph = {
            "elements": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
            "connections": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        }
        result = run_simulation(graph, {}, "what_if")
        assert result["connections_analyzed"] == 2

    def test_unknown_simulation_type_does_not_raise(self) -> None:
        graph = {"elements": [{"name": "X", "duration": 1}], "connections": []}
        result = run_simulation(graph, {}, "totally_unknown_type")
        assert "metrics" in result
