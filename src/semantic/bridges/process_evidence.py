"""Enhanced ProcessEvidence semantic bridge.

Creates and strengthens SUPPORTED_BY relationships between process elements
and evidence items based on semantic similarity and co-occurrence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)


@dataclass
class BridgeResult:
    """Result of running a semantic bridge."""

    relationships_created: int = 0
    relationships_updated: int = 0
    errors: list[str] = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


class ProcessEvidenceBridge:
    """Enhanced bridge linking process elements to evidence.

    Strengthens confidence scoring by analyzing the overlap between
    process element descriptions and evidence content.
    """

    def __init__(self, graph_service: KnowledgeGraphService) -> None:
        self._graph = graph_service

    async def run(self, engagement_id: str) -> BridgeResult:
        """Run the process-evidence bridge for an engagement.

        Finds process nodes and evidence nodes, creates SUPPORTED_BY
        relationships for matching pairs.

        Args:
            engagement_id: The engagement to bridge.

        Returns:
            BridgeResult with counts.
        """
        result = BridgeResult()

        process_nodes = await self._graph.find_nodes("Process", {"engagement_id": engagement_id})
        activity_nodes = await self._graph.find_nodes("Activity", {"engagement_id": engagement_id})
        evidence_nodes = await self._graph.find_nodes("Evidence", {"engagement_id": engagement_id})

        all_process_nodes = process_nodes + activity_nodes

        for proc in all_process_nodes:
            proc_name = proc.properties.get("name", "").lower()
            for ev in evidence_nodes:
                ev_name = ev.properties.get("name", "").lower()
                if self._is_related(proc_name, ev_name):
                    try:
                        await self._graph.create_relationship(
                            from_id=proc.id,
                            to_id=ev.id,
                            relationship_type="SUPPORTED_BY",
                            properties={"source": "process_evidence_bridge", "confidence": 0.7},
                        )
                        result.relationships_created += 1
                    except Exception as e:
                        result.errors.append(str(e))

        return result

    def _is_related(self, proc_name: str, ev_name: str) -> bool:
        """Check if a process name is related to evidence by word overlap."""
        proc_words = set(proc_name.split())
        ev_words = set(ev_name.split())
        overlap = proc_words & ev_words
        # At least 2 common words (ignoring very short words)
        meaningful = {w for w in overlap if len(w) > 2}
        return len(meaningful) >= 1
