"""ProcessTOM semantic bridge.

Creates IMPLEMENTS relationships between process elements and TOM dimensions,
linking discovered processes to target operating model specifications.
"""

from __future__ import annotations

from neo4j.exceptions import Neo4jError

import logging

from src.core.models import TOMDimension
from src.semantic.bridges.process_evidence import BridgeResult
from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)

# Keywords that map process concepts to TOM dimensions
_DIMENSION_KEYWORDS: dict[str, list[str]] = {
    TOMDimension.PROCESS_ARCHITECTURE: ["process", "workflow", "procedure", "step", "activity", "flow"],
    TOMDimension.PEOPLE_AND_ORGANIZATION: ["team", "role", "manager", "department", "staff", "training"],
    TOMDimension.TECHNOLOGY_AND_DATA: ["system", "application", "database", "integration", "api", "data"],
    TOMDimension.GOVERNANCE_STRUCTURES: ["governance", "committee", "approval", "decision", "authority"],
    TOMDimension.PERFORMANCE_MANAGEMENT: ["kpi", "metric", "sla", "performance", "target", "monitor"],
    TOMDimension.RISK_AND_COMPLIANCE: ["risk", "compliance", "audit", "control", "regulation", "policy"],
}


class ProcessTOMBridge:
    """Bridge linking processes to TOM dimensions.

    Analyzes process names and properties to determine which TOM
    dimensions they implement, creating IMPLEMENTS relationships.
    """

    def __init__(self, graph_service: KnowledgeGraphService) -> None:
        self._graph = graph_service

    async def run(self, engagement_id: str) -> BridgeResult:
        """Run the process-TOM bridge for an engagement.

        Args:
            engagement_id: The engagement to bridge.

        Returns:
            BridgeResult with counts.
        """
        result = BridgeResult()

        # Get all process-like nodes
        process_nodes = await self._graph.find_nodes("Process", {"engagement_id": engagement_id})
        activity_nodes = await self._graph.find_nodes("Activity", {"engagement_id": engagement_id})
        tom_nodes = await self._graph.find_nodes("TOM", {"engagement_id": engagement_id})

        all_nodes = process_nodes + activity_nodes

        for node in all_nodes:
            name = node.properties.get("name", "").lower()
            dimensions = self._classify_dimensions(name)

            for dim in dimensions:
                for tom in tom_nodes:
                    try:
                        await self._graph.create_relationship(
                            from_id=node.id,
                            to_id=tom.id,
                            relationship_type="IMPLEMENTS",
                            properties={"dimension": dim, "source": "process_tom_bridge"},
                        )
                        result.relationships_created += 1
                    except Neo4jError as e:
                        result.errors.append(str(e))

        return result

    def _classify_dimensions(self, name: str) -> list[str]:
        """Classify which TOM dimensions a process element relates to."""
        dimensions = []
        words = set(name.split())
        for dim, keywords in _DIMENSION_KEYWORDS.items():
            if any(kw in words or kw in name for kw in keywords):
                dimensions.append(dim)
        return dimensions
