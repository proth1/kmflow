"""Conformance checking algorithm for BPMN process models.

Compares observed process behavior against a reference model
to calculate fitness and precision scores.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.conformance.bpmn_parser import BPMNGraph, parse_bpmn_xml

logger = logging.getLogger(__name__)


@dataclass
class Deviation:
    """A single deviation between observed and reference models."""

    element_name: str
    deviation_type: str  # "missing_activity", "extra_activity", "different_path", "sequence_mismatch"
    severity: str  # "high", "medium", "low"
    description: str
    reference_element_id: str | None = None
    observed_element_id: str | None = None


@dataclass
class ConformanceCheckResult:
    """Result of a conformance check."""

    fitness_score: float  # 0-1, how well observed fits reference
    precision_score: float  # 0-1, how precise observed is
    matching_elements: int
    total_reference_elements: int
    total_observed_elements: int
    deviations: list[Deviation] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class ConformanceChecker:
    """Checks conformance between observed process and reference model."""

    def check(
        self,
        reference_graph: BPMNGraph,
        observed_graph: BPMNGraph,
    ) -> ConformanceCheckResult:
        """Run conformance check between reference and observed models.

        Args:
            reference_graph: The reference (target) process model.
            observed_graph: The observed (as-is) process model.

        Returns:
            ConformanceCheckResult with scores and deviations.
        """
        deviations: list[Deviation] = []

        # Get task sets for comparison (by name, normalized)
        ref_tasks = {self._normalize_name(t.name): t for t in reference_graph.tasks}
        obs_tasks = {self._normalize_name(t.name): t for t in observed_graph.tasks}

        ref_names = set(ref_tasks.keys())
        obs_names = set(obs_tasks.keys())

        # Find matching elements
        matching_names = ref_names & obs_names
        matching_count = len(matching_names)

        # Missing activities (in reference but not observed)
        missing = ref_names - obs_names
        for name in missing:
            ref_elem = ref_tasks[name]
            deviations.append(
                Deviation(
                    element_name=ref_elem.name,
                    deviation_type="missing_activity",
                    severity="high",
                    description=f"Activity '{ref_elem.name}' exists in reference model but not in observed process",
                    reference_element_id=ref_elem.id,
                )
            )

        # Extra activities (in observed but not reference)
        extra = obs_names - ref_names
        for name in extra:
            obs_elem = obs_tasks[name]
            deviations.append(
                Deviation(
                    element_name=obs_elem.name,
                    deviation_type="extra_activity",
                    severity="medium",
                    description=f"Activity '{obs_elem.name}' found in observed process but not in reference model",
                    observed_element_id=obs_elem.id,
                )
            )

        # Check sequence differences for matching elements
        sequence_deviations = self._check_sequences(
            reference_graph, observed_graph, matching_names, ref_tasks, obs_tasks
        )
        deviations.extend(sequence_deviations)

        # Calculate scores
        total_ref = max(len(ref_names), 1)
        total_obs = max(len(obs_names), 1)
        fitness = matching_count / total_ref
        precision = matching_count / total_obs if total_obs > 0 else 0.0

        return ConformanceCheckResult(
            fitness_score=round(fitness, 4),
            precision_score=round(precision, 4),
            matching_elements=matching_count,
            total_reference_elements=len(ref_names),
            total_observed_elements=len(obs_names),
            deviations=deviations,
            details={
                "matching_activities": sorted(matching_names),
                "missing_activities": sorted(missing),
                "extra_activities": sorted(extra),
            },
        )

    def check_from_xml(
        self,
        reference_xml: str,
        observed_xml: str,
    ) -> ConformanceCheckResult:
        """Convenience method to check conformance from raw BPMN XML."""
        ref_graph = parse_bpmn_xml(reference_xml)
        obs_graph = parse_bpmn_xml(observed_xml)
        return self.check(ref_graph, obs_graph)

    def _normalize_name(self, name: str) -> str:
        """Normalize element name for comparison."""
        return name.strip().lower().replace("_", " ").replace("-", " ")

    def _check_sequences(
        self,
        ref_graph: BPMNGraph,
        obs_graph: BPMNGraph,
        matching_names: set[str],
        ref_tasks: dict[str, Any],
        obs_tasks: dict[str, Any],
    ) -> list[Deviation]:
        """Check if matching activities have the same sequence relationships."""
        deviations = []

        for name in matching_names:
            ref_elem = ref_tasks[name]
            obs_elem = obs_tasks[name]

            # Get successors in reference
            ref_successors = set()
            for target_id in ref_graph.adjacency.get(ref_elem.id, []):
                if target_id in ref_graph.elements:
                    ref_successors.add(self._normalize_name(ref_graph.elements[target_id].name))

            # Get successors in observed
            obs_successors = set()
            for target_id in obs_graph.adjacency.get(obs_elem.id, []):
                if target_id in obs_graph.elements:
                    obs_successors.add(self._normalize_name(obs_graph.elements[target_id].name))

            # Check for sequence differences (only for matching successors)
            diff = (ref_successors & matching_names) ^ (obs_successors & matching_names)
            if diff:
                deviations.append(
                    Deviation(
                        element_name=ref_elem.name,
                        deviation_type="sequence_mismatch",
                        severity="low",
                        description=f"Activity '{ref_elem.name}' has different successor relationships",
                        reference_element_id=ref_elem.id,
                        observed_element_id=obs_elem.id,
                    )
                )

        return deviations
