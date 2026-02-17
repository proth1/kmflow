"""EvidencePolicy semantic bridge.

Creates GOVERNED_BY relationships between evidence items and policies
when evidence content references policy-related terms.
"""

from __future__ import annotations

import logging
from typing import Any

from src.semantic.bridges.process_evidence import BridgeResult
from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)


class EvidencePolicyBridge:
    """Bridge linking evidence to policies.

    Detects when evidence content references policy-related concepts
    and creates GOVERNED_BY relationships in the graph.
    """

    def __init__(self, graph_service: KnowledgeGraphService) -> None:
        self._graph = graph_service

    async def run(self, engagement_id: str) -> BridgeResult:
        """Run the evidence-policy bridge for an engagement.

        Args:
            engagement_id: The engagement to bridge.

        Returns:
            BridgeResult with counts.
        """
        result = BridgeResult()

        evidence_nodes = await self._graph.find_nodes("Evidence", {"engagement_id": engagement_id})
        policy_nodes = await self._graph.find_nodes("Policy", {"engagement_id": engagement_id})

        for ev in evidence_nodes:
            ev_name = ev.properties.get("name", "").lower()
            for policy in policy_nodes:
                policy_name = policy.properties.get("name", "").lower()
                if self._references_policy(ev_name, policy_name):
                    try:
                        await self._graph.create_relationship(
                            from_id=ev.id,
                            to_id=policy.id,
                            relationship_type="GOVERNED_BY",
                            properties={"source": "evidence_policy_bridge"},
                        )
                        result.relationships_created += 1
                    except Exception as e:
                        result.errors.append(str(e))

        return result

    def _references_policy(self, ev_name: str, policy_name: str) -> bool:
        """Check if evidence references a policy by name overlap."""
        policy_words = {w for w in policy_name.split() if len(w) > 3}
        ev_words = set(ev_name.split())
        return len(policy_words & ev_words) >= 1
