"""Semantic service API routes (KMFLOW-67).

Exposes entity extraction, hybrid retrieval, and embedding generation
as REST endpoints for external integrations and frontend consumption.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.auth import get_current_user
from src.core.models import User
from src.core.permissions import require_engagement_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/semantic", tags=["semantic"])


# -- Request/Response Schemas ------------------------------------------------


class EntityExtractionRequest(BaseModel):
    """Request to extract entities from text."""

    text: str = Field(..., min_length=1, max_length=50000, description="Text to extract entities from")
    use_llm: bool = Field(False, description="Use LLM-based extraction (higher accuracy)")
    seed_terms: list[str] | None = Field(None, description="Seed terms for confidence boosting")


class ExtractedEntityResponse(BaseModel):
    """A single extracted entity."""

    id: str
    entity_type: str
    name: str
    confidence: float
    source_span: str = ""
    aliases: list[str] = []
    metadata: dict[str, str] = {}


class EntityExtractionResponse(BaseModel):
    """Response from entity extraction."""

    entities: list[ExtractedEntityResponse]
    entity_count: int
    by_type: dict[str, int]
    raw_text_length: int


class EntityResolutionRequest(BaseModel):
    """Request to resolve duplicate entities."""

    entities: list[ExtractedEntityResponse]


class DuplicateCandidateResponse(BaseModel):
    """A pair of entities flagged as potential duplicates."""

    entity_a_id: str
    entity_b_id: str
    entity_a_name: str
    entity_b_name: str
    entity_type: str
    similarity_reason: str


class EntityResolutionResponse(BaseModel):
    """Response from entity resolution."""

    resolved_entities: list[ExtractedEntityResponse]
    duplicates_found: list[DuplicateCandidateResponse]
    merged_count: int


class EmbeddingRequest(BaseModel):
    """Request to generate embeddings for text."""

    texts: list[str] = Field(..., min_length=1, max_length=100, description="Texts to embed (max 100)")


class EmbeddingResponse(BaseModel):
    """Response with generated embeddings."""

    embeddings: list[list[float]]
    dimension: int
    count: int


class SemanticSearchRequest(BaseModel):
    """Request for semantic similarity search."""

    query: str = Field(..., min_length=1, max_length=5000, description="Search query text")
    top_k: int = Field(10, ge=1, le=100, description="Number of results to return")


class SemanticSearchResult(BaseModel):
    """A single semantic search result."""

    content: str
    source_id: str
    source_type: str
    similarity_score: float
    metadata: dict[str, Any] = {}


class SemanticSearchResponse(BaseModel):
    """Response from semantic search."""

    results: list[SemanticSearchResult]
    query: str
    total_results: int


# -- Endpoints ---------------------------------------------------------------


@router.post("/extract", response_model=EntityExtractionResponse)
async def extract_entities_endpoint(
    body: EntityExtractionRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Extract entities from arbitrary text.

    Uses rule-based NLP patterns to identify activities, decisions, roles,
    systems, and documents. Optionally uses LLM for higher accuracy.
    """
    from src.semantic.entity_extraction import extract_entities

    result = await extract_entities(
        text=body.text,
        use_llm=body.use_llm,
        seed_terms=body.seed_terms,
    )

    by_type: dict[str, int] = {}
    for entity in result.entities:
        et = entity.entity_type.value if hasattr(entity.entity_type, "value") else str(entity.entity_type)
        by_type[et] = by_type.get(et, 0) + 1

    return {
        "entities": [
            {
                "id": e.id,
                "entity_type": e.entity_type.value if hasattr(e.entity_type, "value") else str(e.entity_type),
                "name": e.name,
                "confidence": e.confidence,
                "source_span": e.source_span,
                "aliases": e.aliases,
                "metadata": e.metadata,
            }
            for e in result.entities
        ],
        "entity_count": len(result.entities),
        "by_type": by_type,
        "raw_text_length": result.raw_text_length,
    }


@router.post("/resolve", response_model=EntityResolutionResponse)
async def resolve_entities_endpoint(
    body: EntityResolutionRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Resolve duplicate entities by merging near-duplicates.

    Takes a list of entities and merges those that refer to the same concept
    based on normalized name comparison.
    """
    from src.semantic.entity_extraction import (
        EntityType,
        ExtractedEntity,
        resolve_entities,
    )

    entities = [
        ExtractedEntity(
            id=e.id,
            entity_type=EntityType(e.entity_type),
            name=e.name,
            confidence=e.confidence,
            source_span=e.source_span,
            aliases=e.aliases,
            metadata=e.metadata,
        )
        for e in body.entities
    ]

    resolved, duplicates = resolve_entities(entities)

    return {
        "resolved_entities": [
            {
                "id": e.id,
                "entity_type": e.entity_type.value,
                "name": e.name,
                "confidence": e.confidence,
                "source_span": e.source_span,
                "aliases": e.aliases,
                "metadata": e.metadata,
            }
            for e in resolved
        ],
        "duplicates_found": [
            {
                "entity_a_id": d.entity_a_id,
                "entity_b_id": d.entity_b_id,
                "entity_a_name": d.entity_a_name,
                "entity_b_name": d.entity_b_name,
                "entity_type": d.entity_type.value if hasattr(d.entity_type, "value") else str(d.entity_type),
                "similarity_reason": d.similarity_reason,
            }
            for d in duplicates
        ],
        "merged_count": len(entities) - len(resolved),
    }


@router.post("/embed", response_model=EmbeddingResponse)
async def generate_embeddings_endpoint(
    body: EmbeddingRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate embeddings for a list of texts.

    Uses the configured embedding model (default: all-mpnet-base-v2)
    to produce dense vector representations for semantic comparison.
    """
    from src.semantic.embeddings import get_embedding_service

    service = get_embedding_service()
    embeddings = service.generate_embeddings_batch(body.texts)

    return {
        "embeddings": embeddings,
        "dimension": service.dimension,
        "count": len(embeddings),
    }


@router.post(
    "/search/{engagement_id}",
    response_model=SemanticSearchResponse,
)
async def semantic_search_endpoint(
    engagement_id: UUID,
    body: SemanticSearchRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Search evidence fragments by semantic similarity.

    Combines pgvector cosine similarity with optional Neo4j graph expansion
    for hybrid retrieval. Results are scoped to the specified engagement.
    """
    from src.rag.retrieval import HybridRetriever

    retriever = HybridRetriever()
    results = await retriever.retrieve(
        query=body.query,
        session=session,
        engagement_id=str(engagement_id),
        top_k=body.top_k,
    )

    return {
        "results": [
            {
                "content": r.content,
                "source_id": r.source_id,
                "source_type": r.source_type,
                "similarity_score": r.similarity_score,
                "metadata": r.metadata,
            }
            for r in results
        ],
        "query": body.query,
        "total_results": len(results),
    }


@router.get("/entities/{engagement_id}")
async def list_engagement_entities(
    engagement_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_engagement_access),
    entity_type: str | None = Query(
        None, description="Filter by entity type (activity, role, system, decision, document)"
    ),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List extracted entities for an engagement from the knowledge graph.

    Queries Neo4j for all entities linked to the engagement's evidence,
    with optional filtering by type and confidence threshold.
    """
    from src.semantic.graph import KnowledgeGraphService

    graph_service = KnowledgeGraphService(request.app.state.neo4j_driver)

    # Map entity types to Neo4j node labels
    label_map = {
        "activity": "Activity",
        "role": "Role",
        "system": "System",
        "decision": "Decision",
        "document": "Document",
    }

    labels_to_query = [label_map[entity_type]] if entity_type and entity_type in label_map else list(label_map.values())

    all_entities: list[dict[str, Any]] = []
    for label in labels_to_query:
        try:
            nodes = await graph_service.find_nodes(
                label=label,
                filters={"engagement_id": str(engagement_id)},
                limit=limit,
            )
            for node in nodes:
                confidence = node.properties.get("confidence", 0.0)
                if isinstance(confidence, int | float) and confidence >= min_confidence:
                    all_entities.append(
                        {
                            "id": node.id,
                            "label": node.label,
                            "name": node.properties.get("name", ""),
                            "confidence": confidence,
                            "properties": node.properties,
                        }
                    )
        except ValueError:
            logger.debug("Skipping invalid label %s for engagement %s", label, engagement_id)
            continue
        except Exception:
            logger.warning("Failed to query label %s for engagement %s", label, engagement_id, exc_info=True)
            continue

    # Sort by confidence descending, apply offset/limit
    all_entities.sort(key=lambda e: e.get("confidence", 0.0), reverse=True)
    paginated = all_entities[offset : offset + limit]

    return {
        "entities": paginated,
        "engagement_id": str(engagement_id),
        "total": len(all_entities),
        "limit": limit,
        "offset": offset,
    }
