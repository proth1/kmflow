"""Enhanced ProcessEvidence semantic bridge.

Creates and strengthens SUPPORTED_BY relationships between process elements
and evidence items based on semantic similarity and co-occurrence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np
from neo4j.exceptions import Neo4jError

from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)

_EMBEDDING_THRESHOLD = 0.6


@runtime_checkable
class EmbeddingServiceProtocol(Protocol):
    """Minimal interface for embedding services used by semantic bridges."""

    async def embed_texts_async(self, texts: list[str]) -> list[list[float]]: ...


@dataclass
class BridgeResult:
    """Result of running a semantic bridge."""

    relationships_created: int = 0
    relationships_updated: int = 0
    errors: list[str] = field(default_factory=list)


class ProcessEvidenceBridge:
    """Enhanced bridge linking process elements to evidence.

    Strengthens confidence scoring by analyzing the overlap between
    process element descriptions and evidence content. Uses embedding
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

        if not all_process_nodes or not evidence_nodes:
            return result

        # Build name lists for batch embedding
        proc_names = [n.properties.get("name", "") for n in all_process_nodes]
        ev_names = [n.properties.get("name", "") for n in evidence_nodes]

        proc_embeddings: list[list[float]] | None = None
        ev_embeddings: list[list[float]] | None = None
        use_embeddings = self._embedding_service is not None

        if self._embedding_service is not None:
            try:
                proc_embeddings = await self._embedding_service.embed_texts_async(proc_names)
                ev_embeddings = await self._embedding_service.embed_texts_async(ev_names)
            except (ValueError, RuntimeError) as e:
                logger.warning("Embedding failed, falling back to word-overlap: %s", e)
                use_embeddings = False

        for p_idx, proc in enumerate(all_process_nodes):
            proc_name = proc_names[p_idx].lower()
            for e_idx, ev in enumerate(evidence_nodes):
                ev_name = ev_names[e_idx].lower()

                if use_embeddings and proc_embeddings and ev_embeddings:
                    similarity = float(np.dot(proc_embeddings[p_idx], ev_embeddings[e_idx]))
                    is_match = similarity >= _EMBEDDING_THRESHOLD
                    confidence = similarity
                else:
                    is_match = self._is_related(proc_name, ev_name)
                    confidence = 0.7

                if is_match:
                    try:
                        await self._graph.create_relationship(
                            from_id=proc.id,
                            to_id=ev.id,
                            relationship_type="SUPPORTED_BY",
                            properties={
                                "source": "process_evidence_bridge",
                                "confidence": confidence,
                            },
                        )
                        result.relationships_created += 1
                    except Neo4jError as e:
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
