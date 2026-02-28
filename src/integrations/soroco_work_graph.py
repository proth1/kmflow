"""Soroco Scout Work Graph integration for desktop task mining evidence (Story #326).

Extends the existing SorocoConnector with Work Graph API support:
- Fetches desktop activities from ``/v1/workgraphs/{graph_id}/activities``
- Maps Scout activities to Activity nodes with ``epistemic_frame="telemetric"``
- Creates SUPPORTED_BY edges for cross-source triangulation readiness

Activities captured by Soroco Scout are imported as KMFlow evidence
category 7 (KM4Work) and carry telemetric epistemic frames to distinguish
them from documentary or interview-sourced process elements.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Evidence category for KM4Work (desktop task mining data)
EVIDENCE_CATEGORY_KM4WORK = 7


@dataclass
class ScoutActivity:
    """A single desktop activity from Soroco Scout Work Graph.

    Attributes:
        activity_id: Unique Scout activity identifier.
        activity_name: Human-readable activity name.
        application: Desktop application used.
        user: Desktop user who performed the activity.
        start_time: ISO 8601 start timestamp.
        end_time: ISO 8601 end timestamp.
        duration_ms: Duration in milliseconds.
        actions: List of sub-actions within the activity.
        graph_id: Work graph this activity belongs to.
    """

    activity_id: str
    activity_name: str
    application: str = ""
    user: str = ""
    start_time: str = ""
    end_time: str = ""
    duration_ms: int = 0
    actions: list[dict[str, Any]] = field(default_factory=list)
    graph_id: str = ""

    @classmethod
    def from_api_response(cls, data: dict[str, Any], graph_id: str = "") -> ScoutActivity:
        """Create a ScoutActivity from a Scout API response dict."""
        return cls(
            activity_id=str(data.get("activity_id", data.get("id", ""))),
            activity_name=data.get("activity_name", data.get("name", "")),
            application=data.get("application", ""),
            user=data.get("user", data.get("user_id", "")),
            start_time=data.get("start_time", ""),
            end_time=data.get("end_time", ""),
            duration_ms=int(data.get("duration_ms", 0)),
            actions=data.get("actions", []),
            graph_id=graph_id,
        )


@dataclass
class ProcessElementMapping:
    """Mapping of a Scout activity to a KMFlow ProcessElement node.

    Attributes:
        element_id: Generated KMFlow ProcessElement node ID.
        activity: Source Scout activity.
        name: Element name (from activity_name).
        epistemic_frame: Always "telemetric" for task mining data.
        performed_by: Desktop user role (PERFORMED_BY edge target).
        evidence_category: KMFlow evidence category (7 = KM4Work).
        source: Source system identifier.
        attributes: Additional properties for the graph node.
    """

    element_id: str
    activity: ScoutActivity
    name: str
    epistemic_frame: str = "telemetric"
    performed_by: str = ""
    evidence_category: int = EVIDENCE_CATEGORY_KM4WORK
    source: str = "soroco_scout"
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkGraphImportResult:
    """Result of importing a Soroco Work Graph.

    Attributes:
        graph_id: The work graph that was imported.
        engagement_id: The KMFlow engagement this import belongs to.
        activities: List of imported Scout activities.
        element_mappings: ProcessElement mappings for each activity.
        evidence_records: Evidence records created (category 7).
        graph_operations: Neo4j graph operations for node/edge merges.
        errors: Any errors encountered during import.
    """

    graph_id: str = ""
    engagement_id: str = ""
    activities: list[ScoutActivity] = field(default_factory=list)
    element_mappings: list[ProcessElementMapping] = field(default_factory=list)
    evidence_records: list[dict[str, Any]] = field(default_factory=list)
    graph_operations: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.activities) > 0 and len(self.errors) == 0

    @property
    def activity_count(self) -> int:
        return len(self.activities)

    @property
    def element_count(self) -> int:
        return len(self.element_mappings)


class SorocoWorkGraphMapper:
    """Maps Soroco Scout activities to KMFlow Activity nodes.

    Handles the transformation from Scout Work Graph activities to
    Activity nodes with telemetric epistemic frames and
    PERFORMED_BY / SUPPORTED_BY edge generation.
    """

    def __init__(self, engagement_id: str) -> None:
        self._engagement_id = engagement_id

    def map_activity(self, activity: ScoutActivity) -> ProcessElementMapping:
        """Map a single Scout activity to a ProcessElement.

        Args:
            activity: The Scout activity to map.

        Returns:
            ProcessElementMapping with telemetric epistemic frame.
        """
        element_id = f"scout:{activity.activity_id}"

        return ProcessElementMapping(
            element_id=element_id,
            activity=activity,
            name=activity.activity_name,
            epistemic_frame="telemetric",
            performed_by=activity.user,
            evidence_category=EVIDENCE_CATEGORY_KM4WORK,
            source="soroco_scout",
            attributes={
                "application": activity.application,
                "duration_ms": activity.duration_ms,
                "start_time": activity.start_time,
                "end_time": activity.end_time,
                "graph_id": activity.graph_id,
                "action_count": len(activity.actions),
            },
        )

    def map_activities(self, activities: list[ScoutActivity]) -> list[ProcessElementMapping]:
        """Map a batch of Scout activities to ProcessElements.

        Args:
            activities: List of Scout activities.

        Returns:
            List of ProcessElementMappings.
        """
        return [self.map_activity(a) for a in activities]

    def build_evidence_record(self, mapping: ProcessElementMapping) -> dict[str, Any]:
        """Build a KMFlow evidence record (category 7) from a mapping.

        Args:
            mapping: The ProcessElement mapping.

        Returns:
            Evidence record dict for persistence.
        """
        return {
            "engagement_id": self._engagement_id,
            "name": f"soroco_activity_{mapping.activity.activity_id}",
            "category": EVIDENCE_CATEGORY_KM4WORK,
            "format": "json",
            "source_system": "soroco_scout",
            "source": "soroco_scout",
            "epistemic_frame": "telemetric",
            "metadata": {
                "activity_id": mapping.activity.activity_id,
                "activity_name": mapping.activity.activity_name,
                "application": mapping.activity.application,
                "user": mapping.activity.user,
                "graph_id": mapping.activity.graph_id,
                "duration_ms": mapping.activity.duration_ms,
            },
        }

    def build_graph_operations(self, mappings: list[ProcessElementMapping]) -> list[dict[str, Any]]:
        """Build Neo4j graph operations for the mapped elements.

        Generates operations to:
        1. MERGE Activity nodes with epistemic_frame="telemetric"
        2. Create PERFORMED_BY edges to user Role nodes
        3. Create SUPPORTED_BY edges linking activities to Evidence records

        Args:
            mappings: List of ProcessElement mappings.

        Returns:
            List of graph operation dicts (node_ops and edge_ops).
        """
        operations: list[dict[str, Any]] = []

        for mapping in mappings:
            # Node operation: create/merge Activity
            operations.append(
                {
                    "op": "merge_node",
                    "label": "Activity",
                    "id": mapping.element_id,
                    "properties": {
                        "name": mapping.name,
                        "engagement_id": self._engagement_id,
                        "epistemic_frame": mapping.epistemic_frame,
                        "source_system": mapping.source,
                        "evidence_category": mapping.evidence_category,
                        **mapping.attributes,
                    },
                }
            )

            # PERFORMED_BY edge to user role
            if mapping.performed_by:
                operations.append(
                    {
                        "op": "merge_edge",
                        "type": "PERFORMED_BY",
                        "from_id": mapping.element_id,
                        "to_label": "Role",
                        "to_id": f"role:{mapping.performed_by}",
                        "to_properties": {
                            "name": mapping.performed_by,
                            "engagement_id": self._engagement_id,
                        },
                    }
                )

            # SUPPORTED_BY edge to evidence record
            evidence_id = f"evidence:soroco:{mapping.activity.activity_id}"
            operations.append(
                {
                    "op": "merge_edge",
                    "type": "SUPPORTED_BY",
                    "from_id": mapping.element_id,
                    "to_label": "Evidence",
                    "to_id": evidence_id,
                    "to_properties": {
                        "source": "soroco_scout",
                        "category": EVIDENCE_CATEGORY_KM4WORK,
                        "epistemic_frame": "telemetric",
                        "engagement_id": self._engagement_id,
                    },
                }
            )

        return operations


def import_work_graph(
    activities_data: list[dict[str, Any]],
    graph_id: str,
    engagement_id: str,
) -> WorkGraphImportResult:
    """Import a batch of Scout work graph activities.

    Parses raw API response data into ScoutActivities, maps them to
    ProcessElements, and generates evidence records and graph operations.

    Args:
        activities_data: Raw activity dicts from the Scout API.
        graph_id: The work graph identifier.
        engagement_id: The KMFlow engagement ID.

    Returns:
        WorkGraphImportResult with all mappings and evidence records.
    """
    result = WorkGraphImportResult(
        graph_id=graph_id,
        engagement_id=engagement_id,
    )

    # Parse activities
    for data in activities_data:
        try:
            activity = ScoutActivity.from_api_response(data, graph_id=graph_id)
            if not activity.activity_id:
                result.errors.append(f"Activity missing ID: {data}")
                continue
            result.activities.append(activity)
        except (KeyError, ValueError, TypeError) as exc:
            result.errors.append(f"Failed to parse activity: {exc}")

    # Map to ProcessElements
    mapper = SorocoWorkGraphMapper(engagement_id)
    result.element_mappings = mapper.map_activities(result.activities)

    # Build evidence records and graph operations
    for mapping in result.element_mappings:
        result.evidence_records.append(mapper.build_evidence_record(mapping))
    result.graph_operations = mapper.build_graph_operations(result.element_mappings)

    logger.info(
        "Work graph import: %d activities, %d elements from graph %s",
        result.activity_count,
        result.element_count,
        graph_id,
    )

    return result
