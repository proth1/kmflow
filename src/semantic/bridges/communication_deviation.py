"""CommunicationDeviation semantic bridge.

Detects deviations between official process definitions and actual
communication patterns, creating DEVIATES_FROM relationships.
"""

from __future__ import annotations

from neo4j.exceptions import Neo4jError

import logging

from src.semantic.bridges.process_evidence import BridgeResult
from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)

# Keywords indicating process workarounds or deviations
_DEVIATION_KEYWORDS = frozenset(
    {
        "workaround",
        "exception",
        "bypass",
        "skip",
        "instead",
        "actually",
        "really",
        "unofficial",
        "shortcut",
        "override",
        "not following",
        "different from",
        "don't follow",
    }
)


class CommunicationDeviationBridge:
    """Bridge detecting deviations from official processes in communications.

    Analyzes communication evidence for indicators of process deviations
    and creates DEVIATES_FROM relationships between the communication
    evidence and the relevant processes.
    """

    def __init__(self, graph_service: KnowledgeGraphService) -> None:
        self._graph = graph_service

    async def run(self, engagement_id: str) -> BridgeResult:
        """Run the communication-deviation bridge for an engagement.

        Args:
            engagement_id: The engagement to analyze.

        Returns:
            BridgeResult with counts.
        """
        result = BridgeResult()

        evidence_nodes = await self._graph.find_nodes("Evidence", {"engagement_id": engagement_id})
        process_nodes = await self._graph.find_nodes("Process", {"engagement_id": engagement_id})
        activity_nodes = await self._graph.find_nodes("Activity", {"engagement_id": engagement_id})

        all_processes = process_nodes + activity_nodes

        for ev in evidence_nodes:
            ev_name = ev.properties.get("name", "").lower()
            if not self._indicates_deviation(ev_name):
                continue

            # Link to most relevant process
            for proc in all_processes:
                proc_name = proc.properties.get("name", "").lower()
                if self._is_related_to_process(ev_name, proc_name):
                    try:
                        await self._graph.create_relationship(
                            from_id=ev.id,
                            to_id=proc.id,
                            relationship_type="DEVIATES_FROM",
                            properties={"source": "communication_deviation_bridge"},
                        )
                        result.relationships_created += 1
                    except Neo4jError as e:
                        result.errors.append(str(e))

        return result

    def _indicates_deviation(self, text: str) -> bool:
        """Check if text contains deviation indicators."""
        return any(kw in text for kw in _DEVIATION_KEYWORDS)

    def _is_related_to_process(self, ev_text: str, proc_name: str) -> bool:
        """Check if evidence text is related to a specific process."""
        proc_words = {w for w in proc_name.split() if len(w) > 2}
        return any(w in ev_text for w in proc_words)
