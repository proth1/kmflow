"""Performance benchmark tests for conformance checker.

Validates that conformance checking completes within time budgets
for models of various sizes (50, 200, 500 elements).
"""

from __future__ import annotations

import time

from src.conformance.bpmn_parser import BPMNElement, BPMNGraph
from src.conformance.checker import ConformanceChecker


def _make_graph(num_tasks: int, prefix: str = "Task") -> BPMNGraph:
    """Create a synthetic BPMNGraph with the specified number of tasks."""
    elements: dict[str, BPMNElement] = {}
    adjacency: dict[str, list[str]] = {}

    for i in range(num_tasks):
        elem_id = f"{prefix}_{i}"
        elem = BPMNElement(id=elem_id, name=f"{prefix} {i}", element_type="task")
        elements[elem_id] = elem
        if i > 0:
            prev_id = f"{prefix}_{i - 1}"
            adjacency.setdefault(prev_id, []).append(elem_id)

    return BPMNGraph(
        elements=elements,
        adjacency=adjacency,
    )


class TestConformancePerformance:
    """Benchmark tests for conformance checker at various model sizes."""

    def setup_method(self):
        self.checker = ConformanceChecker()

    def test_50_elements_under_100ms(self):
        """50-element models should check in under 100ms."""
        ref = _make_graph(50, "Ref")
        obs = _make_graph(45, "Ref")  # 90% overlap by sharing prefix

        start = time.perf_counter()
        result = self.checker.check(ref, obs)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 100, f"50-element check took {elapsed_ms:.1f}ms"
        assert result.fitness_score > 0
        assert result.total_reference_elements == 50

    def test_200_elements_under_500ms(self):
        """200-element models should check in under 500ms."""
        ref = _make_graph(200, "Ref")
        obs = _make_graph(180, "Ref")

        start = time.perf_counter()
        result = self.checker.check(ref, obs)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 500, f"200-element check took {elapsed_ms:.1f}ms"
        assert result.fitness_score > 0

    def test_500_elements_under_2000ms(self):
        """500-element models should check in under 2 seconds."""
        ref = _make_graph(500, "Ref")
        obs = _make_graph(480, "Ref")

        start = time.perf_counter()
        result = self.checker.check(ref, obs)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 2000, f"500-element check took {elapsed_ms:.1f}ms"
        assert result.fitness_score > 0
        assert result.matching_elements > 0

    def test_identical_models_perfect_score(self):
        """Identical models should give fitness=1.0, precision=1.0."""
        ref = _make_graph(100, "Task")
        obs = _make_graph(100, "Task")

        result = self.checker.check(ref, obs)

        assert result.fitness_score == 1.0
        assert result.precision_score == 1.0
        assert len(result.deviations) == 0

    def test_empty_observed_model(self):
        """Empty observed model should give fitness=0."""
        ref = _make_graph(50, "Task")
        obs = BPMNGraph()

        result = self.checker.check(ref, obs)

        assert result.fitness_score == 0.0
