"""EvidencePolicy semantic bridge.

Creates GOVERNED_BY relationships between evidence items and policies
when evidence content references policy-related terms.
"""

from __future__ import annotations

from neo4j.exceptions import Neo4jError

import logging

import numpy as np

from src.semantic.bridges.process_evidence import BridgeResult, EmbeddingServiceProtocol
from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)

_EMBEDDING_THRESHOLD = 0.6


class EvidencePolicyBridge:
    """Bridge linking evidence to policies.

    Detects when evidence content references policy-related concepts
    and creates GOVERNED_BY relationships in the graph. Uses embedding
    cosine similarity when an EmbeddingService is provided; falls back
    to word-overlap matching otherwise.
    """

    def __init__(
        self,
        graph_service: KnowledgeGraphService,
        embedding_service: EmbeddingServiceProtocol | None = None,
    ) -> None:
        self._graph = graph_service
        self._embedding_service = embedding_service

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

        if not evidence_nodes or not policy_nodes:
            return result

        ev_names = [n.properties.get("name", "") for n in evidence_nodes]
        policy_names = [n.properties.get("name", "") for n in policy_nodes]

        ev_embeddings: list[list[float]] | None = None
        policy_embeddings: list[list[float]] | None = None
        use_embeddings = self._embedding_service is not None

        if self._embedding_service is not None:
            try:
                ev_embeddings = await self._embedding_service.embed_texts_async(ev_names)
                policy_embeddings = await self._embedding_service.embed_texts_async(policy_names)
            except (ValueError, RuntimeError) as e:
                logger.warning("Embedding failed, falling back to word-overlap: %s", e)
                use_embeddings = False

        for e_idx, ev in enumerate(evidence_nodes):
            ev_name = ev_names[e_idx].lower()
            for p_idx, policy in enumerate(policy_nodes):
                policy_name = policy_names[p_idx].lower()

                if use_embeddings and ev_embeddings and policy_embeddings:
                    similarity = float(np.dot(ev_embeddings[e_idx], policy_embeddings[p_idx]))
                    is_match = similarity >= _EMBEDDING_THRESHOLD
                    sim_score = similarity
                else:
                    is_match = self._references_policy(ev_name, policy_name)
                    sim_score = 0.7

                if is_match:
                    try:
                        await self._graph.create_relationship(
                            from_id=ev.id,
                            to_id=policy.id,
                            relationship_type="GOVERNED_BY",
                            properties={
                                "source": "evidence_policy_bridge",
                                "similarity_score": sim_score,
                            },
                        )
                        result.relationships_created += 1
                    except Neo4jError as e:
                        result.errors.append(str(e))

        return result

    def _references_policy(self, ev_name: str, policy_name: str) -> bool:
        """Check if evidence references a policy by name overlap."""
        policy_words = {w for w in policy_name.split() if len(w) > 3}
        ev_words = set(ev_name.split())
        return len(policy_words & ev_words) >= 1
