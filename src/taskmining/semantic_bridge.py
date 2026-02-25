"""Task mining semantic bridge: links observed behavior to documented processes.

Creates SUPPORTS relationships (UserAction → Activity) and MAPS_TO
relationships (Application → System) based on embedding similarity.

Story #227 — Part of Epic #225 (Knowledge Graph Integration).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import numpy as np

from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)

# Similarity thresholds for SUPPORTS relationships
_CONFIRMED_THRESHOLD = 0.7
_SUGGESTED_THRESHOLD = 0.5

# Similarity threshold for MAPS_TO relationships
_MAPS_TO_THRESHOLD = 0.6


@runtime_checkable
class EmbeddingServiceProtocol(Protocol):
    """Minimal interface for embedding services used by semantic bridges."""

    async def embed_texts_async(self, texts: list[str]) -> list[list[float]]: ...


@dataclass
class SemanticBridgeResult:
    """Result summary from running the semantic bridge."""

    supports_confirmed: int = 0
    supports_suggested: int = 0
    maps_to_created: int = 0
    errors: list[str] = field(default_factory=list)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    va = np.array(a, dtype=np.float64)
    vb = np.array(b, dtype=np.float64)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


async def run_semantic_bridge(
    graph_service: KnowledgeGraphService,
    embedding_service: EmbeddingServiceProtocol,
    engagement_id: str,
) -> SemanticBridgeResult:
    """Run the semantic bridge for an engagement.

    Links UserAction nodes to Activity nodes via SUPPORTS relationships
    and Application nodes to System nodes via MAPS_TO relationships.

    Args:
        graph_service: Neo4j knowledge graph service.
        embedding_service: Service for computing text embeddings.
        engagement_id: Engagement to process.

    Returns:
        SemanticBridgeResult with counts.
    """
    result = SemanticBridgeResult()

    # -- SUPPORTS: UserAction → Activity ------------------------------------
    user_actions = await graph_service.find_nodes(
        "UserAction", {"engagement_id": engagement_id}
    )
    activities = await graph_service.find_nodes(
        "Activity", {"engagement_id": engagement_id}
    )

    if user_actions and activities:
        await _link_actions_to_activities(
            graph_service, embedding_service, user_actions, activities, result
        )

    # -- MAPS_TO: Application → System --------------------------------------
    applications = await graph_service.find_nodes(
        "Application", {"engagement_id": engagement_id}
    )
    systems = await graph_service.find_nodes(
        "System", {"engagement_id": engagement_id}
    )

    if applications and systems:
        await _link_apps_to_systems(
            graph_service, embedding_service, applications, systems, result
        )

    logger.info(
        "Semantic bridge complete for engagement %s: "
        "confirmed=%d, suggested=%d, maps_to=%d, errors=%d",
        engagement_id,
        result.supports_confirmed,
        result.supports_suggested,
        result.maps_to_created,
        len(result.errors),
    )
    return result


async def _link_actions_to_activities(
    graph_service: KnowledgeGraphService,
    embedding_service: EmbeddingServiceProtocol,
    user_actions: list[Any],
    activities: list[Any],
    result: SemanticBridgeResult,
) -> None:
    """Create SUPPORTS relationships between UserActions and Activities."""
    # Gather texts for embedding
    ua_texts = [n.properties.get("name", "") for n in user_actions]
    act_texts = [n.properties.get("name", "") for n in activities]

    ua_embeddings = await embedding_service.embed_texts_async(ua_texts)
    act_embeddings = await embedding_service.embed_texts_async(act_texts)

    for i, ua_node in enumerate(user_actions):
        best_sim = 0.0
        best_act_idx = -1

        for j, _act_node in enumerate(activities):
            sim = _cosine_similarity(ua_embeddings[i], act_embeddings[j])
            if sim > best_sim:
                best_sim = sim
                best_act_idx = j

        if best_sim < _SUGGESTED_THRESHOLD or best_act_idx < 0:
            continue

        link_type = "confirmed" if best_sim >= _CONFIRMED_THRESHOLD else "suggested"

        try:
            await graph_service.create_relationship(
                from_id=ua_node.id,
                to_id=activities[best_act_idx].id,
                relationship_type="SUPPORTS",
                properties={
                    "similarity_score": round(best_sim, 4),
                    "link_type": link_type,
                    "source": "task_mining_semantic_bridge",
                },
            )
            if link_type == "confirmed":
                result.supports_confirmed += 1
            else:
                result.supports_suggested += 1
        except Exception as e:
            result.errors.append(f"SUPPORTS link failed: {e}")


async def _link_apps_to_systems(
    graph_service: KnowledgeGraphService,
    embedding_service: EmbeddingServiceProtocol,
    applications: list[Any],
    systems: list[Any],
    result: SemanticBridgeResult,
) -> None:
    """Create MAPS_TO relationships between Applications and Systems."""
    app_texts = [n.properties.get("name", "") for n in applications]
    sys_texts = [n.properties.get("name", "") for n in systems]

    app_embeddings = await embedding_service.embed_texts_async(app_texts)
    sys_embeddings = await embedding_service.embed_texts_async(sys_texts)

    for i, app_node in enumerate(applications):
        best_sim = 0.0
        best_sys_idx = -1

        for j, _sys_node in enumerate(systems):
            sim = _cosine_similarity(app_embeddings[i], sys_embeddings[j])
            if sim > best_sim:
                best_sim = sim
                best_sys_idx = j

        if best_sim < _MAPS_TO_THRESHOLD or best_sys_idx < 0:
            continue

        try:
            await graph_service.create_relationship(
                from_id=app_node.id,
                to_id=systems[best_sys_idx].id,
                relationship_type="MAPS_TO",
                properties={
                    "similarity_score": round(best_sim, 4),
                    "source": "task_mining_semantic_bridge",
                },
            )
            result.maps_to_created += 1
        except Exception as e:
            result.errors.append(f"MAPS_TO link failed: {e}")
