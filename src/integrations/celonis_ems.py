"""Celonis EMS integration: event logs, process models, conformance results (Story #325).

Maps Celonis EMS data to KMFlow's knowledge graph:
- Event logs → CanonicalActivityEvent candidates (idempotent import)
- Process model activities → ProcessElement nodes with PRECEDES edges
- Conformance deviations → ConflictObject candidates (SEQUENCE_MISMATCH, EXISTENCE_MISMATCH)
- Partial import with checkpoint support for API unavailability

Celonis conformance score mapping to KMFlow severity:
  score < 0.6 → HIGH (0.8), 0.6–0.8 → MEDIUM (0.5), > 0.8 → LOW (0.2)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Celonis conformance score thresholds for severity mapping
_SEVERITY_HIGH_THRESHOLD = 0.6
_SEVERITY_MEDIUM_THRESHOLD = 0.8

# Severity values for KMFlow ConflictObjects (0.0–1.0)
SEVERITY_HIGH = 0.8
SEVERITY_MEDIUM = 0.5
SEVERITY_LOW = 0.2


def conformance_score_to_severity(score: float) -> float:
    """Map Celonis conformance score (0–1) to KMFlow severity.

    Lower conformance scores indicate greater deviation:
      < 0.6 → HIGH severity (0.8)
      0.6–0.8 → MEDIUM severity (0.5)
      > 0.8 → LOW severity (0.2)

    Args:
        score: Celonis conformance score between 0.0 and 1.0.

    Returns:
        KMFlow severity value between 0.0 and 1.0.
    """
    if score < _SEVERITY_HIGH_THRESHOLD:
        return SEVERITY_HIGH
    if score < _SEVERITY_MEDIUM_THRESHOLD:
        return SEVERITY_MEDIUM
    return SEVERITY_LOW


@dataclass
class CelonisEvent:
    """A single event from a Celonis EMS event log.

    Attributes:
        case_id: The case identifier.
        activity: Activity name.
        timestamp: ISO 8601 event timestamp.
        resource: Resource or user performing the activity.
        variant: Process variant identifier.
        duration: Duration in seconds (if available).
        event_id: Optional unique event identifier for idempotency.
    """

    case_id: str
    activity: str
    timestamp: str = ""
    resource: str = ""
    variant: str = ""
    duration: float = 0.0
    event_id: str = ""

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> CelonisEvent:
        """Create from Celonis API response dict."""
        return cls(
            case_id=str(data.get("case_id", data.get("caseId", ""))),
            activity=data.get("activity", data.get("activityName", "")),
            timestamp=data.get("timestamp", data.get("eventTime", "")),
            resource=data.get("resource", data.get("user", "")),
            variant=str(data.get("variant", data.get("variantId", ""))),
            duration=float(data.get("duration", 0)),
            event_id=str(data.get("event_id", data.get("eventId", ""))),
        )


@dataclass
class CelonisProcessNode:
    """An activity node from a Celonis process model.

    Attributes:
        node_id: Celonis node identifier.
        activity_name: Activity label.
        frequency: How often this activity occurs.
        avg_duration: Average duration in seconds.
    """

    node_id: str
    activity_name: str
    frequency: int = 0
    avg_duration: float = 0.0

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> CelonisProcessNode:
        """Create from Celonis process model API response."""
        return cls(
            node_id=str(data.get("nodeId", data.get("id", ""))),
            activity_name=data.get("activityName", data.get("name", "")),
            frequency=int(data.get("frequency", 0)),
            avg_duration=float(data.get("avgDuration", data.get("average_duration", 0))),
        )


@dataclass
class CelonisSequenceFlow:
    """A sequence flow edge from a Celonis process model.

    Attributes:
        source_node_id: Source activity node ID.
        target_node_id: Target activity node ID.
        frequency: How often this flow occurs.
    """

    source_node_id: str
    target_node_id: str
    frequency: int = 0

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> CelonisSequenceFlow:
        """Create from Celonis process model API response."""
        return cls(
            source_node_id=str(data.get("sourceNodeId", data.get("from", ""))),
            target_node_id=str(data.get("targetNodeId", data.get("to", ""))),
            frequency=int(data.get("frequency", 0)),
        )


@dataclass
class CelonisDeviation:
    """A conformance deviation from Celonis analysis.

    Attributes:
        deviation_id: Unique deviation identifier.
        deviation_type: Type of deviation (sequence, existence, etc.).
        affected_activity: The activity where deviation was detected.
        expected_activity: What was expected (for sequence deviations).
        conformance_score: Celonis conformance score (0–1).
        case_count: Number of cases exhibiting this deviation.
        description: Human-readable deviation description.
    """

    deviation_id: str
    deviation_type: str
    affected_activity: str
    expected_activity: str = ""
    conformance_score: float = 0.0
    case_count: int = 0
    description: str = ""

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> CelonisDeviation:
        """Create from Celonis conformance API response."""
        return cls(
            deviation_id=str(data.get("deviationId", data.get("id", ""))),
            deviation_type=data.get("deviationType", data.get("type", "sequence")),
            affected_activity=data.get("affectedActivity", data.get("activity", "")),
            expected_activity=data.get("expectedActivity", data.get("expected", "")),
            conformance_score=float(data.get("conformanceScore", data.get("score", 0))),
            case_count=int(data.get("caseCount", data.get("cases", 0))),
            description=data.get("description", ""),
        )


# --- Import results ---


@dataclass
class EventLogImportResult:
    """Result of importing a Celonis event log.

    Attributes:
        events: Parsed events.
        canonical_events: Transformed canonical activity events.
        seen_event_ids: Set of event IDs already imported (for idempotency).
        errors: Any errors during import.
        checkpoint: Last event timestamp for resume support.
        status: Import status (complete, partial, failed).
    """

    events: list[CelonisEvent] = field(default_factory=list)
    canonical_events: list[dict[str, Any]] = field(default_factory=list)
    seen_event_ids: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)
    checkpoint: str = ""
    status: str = "complete"

    @property
    def success(self) -> bool:
        return len(self.events) > 0 and self.status != "failed"

    @property
    def event_count(self) -> int:
        return len(self.events)

    @property
    def new_event_count(self) -> int:
        return len(self.canonical_events)


@dataclass
class ProcessModelImportResult:
    """Result of importing a Celonis process model.

    Attributes:
        nodes: Process model activity nodes.
        flows: Sequence flow edges.
        graph_operations: Neo4j graph operations to execute.
        errors: Any errors during import.
    """

    nodes: list[CelonisProcessNode] = field(default_factory=list)
    flows: list[CelonisSequenceFlow] = field(default_factory=list)
    graph_operations: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.nodes) > 0 and len(self.errors) == 0

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.flows)


@dataclass
class ConformanceImportResult:
    """Result of importing Celonis conformance deviations.

    Attributes:
        deviations: Parsed deviations.
        conflict_candidates: ConflictObject candidates for KMFlow.
        errors: Any errors during import.
    """

    deviations: list[CelonisDeviation] = field(default_factory=list)
    conflict_candidates: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.deviations) > 0 and len(self.errors) == 0

    @property
    def deviation_count(self) -> int:
        return len(self.deviations)


# --- Mappers ---


class CelonisEventMapper:
    """Maps Celonis events to KMFlow canonical activity events."""

    def __init__(self, engagement_id: str, source: str = "celonis_ems") -> None:
        self._engagement_id = engagement_id
        self._source = source

    def to_canonical(self, event: CelonisEvent) -> dict[str, Any]:
        """Transform a Celonis event into a canonical activity event dict.

        Args:
            event: Celonis event to transform.

        Returns:
            Dict matching CanonicalActivityEvent fields.
        """
        return {
            "activity_name": event.activity,
            "timestamp": event.timestamp,
            "actor": event.resource,
            "source_system": self._source,
            "case_id": event.case_id,
            "resource": event.resource,
            "extended_attributes": {
                "variant": event.variant,
                "duration": event.duration,
                "celonis_event_id": event.event_id,
            },
        }


class CelonisProcessModelMapper:
    """Maps Celonis process model to KMFlow graph operations."""

    def __init__(self, engagement_id: str, source: str = "celonis_ems") -> None:
        self._engagement_id = engagement_id
        self._source = source

    def build_graph_operations(
        self,
        nodes: list[CelonisProcessNode],
        flows: list[CelonisSequenceFlow],
    ) -> list[dict[str, Any]]:
        """Generate Neo4j graph operations for the process model.

        Creates:
        - MERGE for each ProcessElement node
        - PRECEDES edges for each sequence flow

        Args:
            nodes: Activity nodes from the Celonis model.
            flows: Sequence flows between activities.

        Returns:
            List of graph operation dicts.
        """
        operations: list[dict[str, Any]] = []

        for node in nodes:
            operations.append({
                "op": "merge_node",
                "label": "ProcessElement",
                "id": f"celonis:{node.node_id}",
                "properties": {
                    "name": node.activity_name,
                    "engagement_id": self._engagement_id,
                    "source_connector": "celonis",
                    "external_id": node.node_id,
                    "frequency": node.frequency,
                    "avg_duration": node.avg_duration,
                },
            })

        for flow in flows:
            operations.append({
                "op": "merge_edge",
                "type": "PRECEDES",
                "from_id": f"celonis:{flow.source_node_id}",
                "to_id": f"celonis:{flow.target_node_id}",
                "properties": {
                    "source_connector": "celonis",
                    "frequency": flow.frequency,
                },
            })

        return operations


class CelonisConformanceMapper:
    """Maps Celonis conformance deviations to KMFlow ConflictObject candidates."""

    def __init__(self, engagement_id: str) -> None:
        self._engagement_id = engagement_id

    def map_deviation(self, deviation: CelonisDeviation) -> dict[str, Any]:
        """Map a single Celonis deviation to a ConflictObject candidate.

        Args:
            deviation: The Celonis deviation to map.

        Returns:
            Dict with ConflictObject fields.
        """
        mismatch_type = self._classify_mismatch(deviation.deviation_type)
        severity = conformance_score_to_severity(deviation.conformance_score)

        return {
            "engagement_id": self._engagement_id,
            "mismatch_type": mismatch_type,
            "severity": severity,
            "source_connector": "celonis",
            "affected_activity": deviation.affected_activity,
            "expected_activity": deviation.expected_activity,
            "case_count": deviation.case_count,
            "conformance_score": deviation.conformance_score,
            "description": deviation.description or self._build_description(deviation),
            "celonis_deviation_id": deviation.deviation_id,
        }

    @staticmethod
    def _classify_mismatch(deviation_type: str) -> str:
        """Map Celonis deviation type to KMFlow MismatchType.

        Args:
            deviation_type: Celonis deviation type string.

        Returns:
            KMFlow MismatchType value.
        """
        lower = deviation_type.lower()
        if "sequence" in lower or "order" in lower or "flow" in lower:
            return "sequence_mismatch"
        if "existence" in lower or "missing" in lower or "skip" in lower:
            return "existence_mismatch"
        if "role" in lower or "resource" in lower:
            return "role_mismatch"
        # Default to sequence_mismatch for unrecognized types
        return "sequence_mismatch"

    @staticmethod
    def _build_description(deviation: CelonisDeviation) -> str:
        """Build a human-readable description for the deviation."""
        if deviation.expected_activity:
            return (
                f"Conformance deviation: expected '{deviation.expected_activity}' "
                f"but found '{deviation.affected_activity}' "
                f"(score: {deviation.conformance_score:.2f}, "
                f"{deviation.case_count} cases)"
            )
        return (
            f"Conformance deviation at '{deviation.affected_activity}' "
            f"(score: {deviation.conformance_score:.2f}, "
            f"{deviation.case_count} cases)"
        )


# --- Import orchestration ---


def import_event_log(
    events_data: list[dict[str, Any]],
    engagement_id: str,
    existing_event_ids: set[str] | None = None,
) -> EventLogImportResult:
    """Import a batch of Celonis events (idempotent).

    Filters out events that have already been imported based on event IDs.

    Args:
        events_data: Raw event dicts from the Celonis API.
        engagement_id: KMFlow engagement ID.
        existing_event_ids: Set of event IDs already imported.

    Returns:
        EventLogImportResult with events and canonical mappings.
    """
    result = EventLogImportResult()
    seen = existing_event_ids or set()
    mapper = CelonisEventMapper(engagement_id)

    for data in events_data:
        try:
            event = CelonisEvent.from_api_response(data)
            if not event.case_id or not event.activity:
                result.errors.append(f"Event missing case_id or activity: {data}")
                continue

            result.events.append(event)

            # Idempotency check
            if event.event_id and event.event_id in seen:
                continue

            canonical = mapper.to_canonical(event)
            result.canonical_events.append(canonical)

            if event.event_id:
                seen.add(event.event_id)
                result.seen_event_ids.add(event.event_id)

            # Track checkpoint as latest timestamp
            if event.timestamp and event.timestamp > result.checkpoint:
                result.checkpoint = event.timestamp

        except (KeyError, ValueError, TypeError) as exc:
            result.errors.append(f"Failed to parse event: {exc}")

    return result


def import_process_model(
    nodes_data: list[dict[str, Any]],
    flows_data: list[dict[str, Any]],
    engagement_id: str,
) -> ProcessModelImportResult:
    """Import a Celonis process model into KMFlow graph operations.

    Args:
        nodes_data: Raw activity node dicts from the Celonis API.
        flows_data: Raw sequence flow dicts from the Celonis API.
        engagement_id: KMFlow engagement ID.

    Returns:
        ProcessModelImportResult with nodes, flows, and graph operations.
    """
    result = ProcessModelImportResult()

    for data in nodes_data:
        try:
            node = CelonisProcessNode.from_api_response(data)
            if not node.node_id:
                result.errors.append(f"Node missing ID: {data}")
                continue
            result.nodes.append(node)
        except (KeyError, ValueError, TypeError) as exc:
            result.errors.append(f"Failed to parse node: {exc}")

    for data in flows_data:
        try:
            flow = CelonisSequenceFlow.from_api_response(data)
            if not flow.source_node_id or not flow.target_node_id:
                result.errors.append(f"Flow missing source or target: {data}")
                continue
            result.flows.append(flow)
        except (KeyError, ValueError, TypeError) as exc:
            result.errors.append(f"Failed to parse flow: {exc}")

    # Generate graph operations
    mapper = CelonisProcessModelMapper(engagement_id)
    result.graph_operations = mapper.build_graph_operations(result.nodes, result.flows)

    logger.info(
        "Celonis process model import: %d nodes, %d flows",
        result.node_count,
        result.edge_count,
    )

    return result


def import_conformance_results(
    deviations_data: list[dict[str, Any]],
    engagement_id: str,
) -> ConformanceImportResult:
    """Import Celonis conformance deviations as ConflictObject candidates.

    Args:
        deviations_data: Raw deviation dicts from the Celonis API.
        engagement_id: KMFlow engagement ID.

    Returns:
        ConformanceImportResult with deviations and conflict candidates.
    """
    result = ConformanceImportResult()
    mapper = CelonisConformanceMapper(engagement_id)

    for data in deviations_data:
        try:
            deviation = CelonisDeviation.from_api_response(data)
            if not deviation.deviation_id:
                result.errors.append(f"Deviation missing ID: {data}")
                continue
            result.deviations.append(deviation)
            result.conflict_candidates.append(mapper.map_deviation(deviation))
        except (KeyError, ValueError, TypeError) as exc:
            result.errors.append(f"Failed to parse deviation: {exc}")

    logger.info(
        "Celonis conformance import: %d deviations, %d conflict candidates",
        result.deviation_count,
        len(result.conflict_candidates),
    )

    return result
