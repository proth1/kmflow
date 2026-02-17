"""Knowledge graph API routes.

Provides endpoints for graph construction, querying, traversal,
semantic search, and engagement subgraph retrieval.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.semantic.builder import KnowledgeGraphBuilder
from src.semantic.embeddings import EmbeddingService
from src.semantic.graph import (
    KnowledgeGraphService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])


# -- Request/Response Schemas ------------------------------------------------


class BuildRequest(BaseModel):
    """Request to trigger graph construction."""

    engagement_id: UUID
    incremental: bool = False


class BuildResponse(BaseModel):
    """Response from graph construction."""

    engagement_id: str
    node_count: int
    relationship_count: int
    nodes_by_label: dict[str, int]
    relationships_by_type: dict[str, int]
    fragments_processed: int
    entities_extracted: int
    entities_resolved: int
    errors: list[str] = Field(default_factory=list)


class NodeResponse(BaseModel):
    """Response for a graph node."""

    id: str
    label: str
    properties: dict[str, Any]


class RelationshipResponse(BaseModel):
    """Response for a graph relationship."""

    id: str
    from_id: str
    to_id: str
    relationship_type: str
    properties: dict[str, Any]


class TraverseRequest(BaseModel):
    """Query parameters for graph traversal."""

    depth: int = Field(default=2, ge=1, le=5)
    relationship_types: list[str] | None = None


class SearchRequest(BaseModel):
    """Request for semantic search."""

    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)
    engagement_id: UUID | None = None


class SearchResult(BaseModel):
    """A single semantic search result."""

    fragment_id: str
    content: str
    evidence_id: str
    similarity_score: float


class StatsResponse(BaseModel):
    """Response for graph statistics."""

    node_count: int
    relationship_count: int
    nodes_by_label: dict[str, int]
    relationships_by_type: dict[str, int]


class SubgraphResponse(BaseModel):
    """Response for engagement subgraph."""

    nodes: list[NodeResponse]
    relationships: list[RelationshipResponse]


class CypherQueryRequest(BaseModel):
    """Request for a read-only Cypher query."""

    query: str = Field(..., min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


# -- Dependencies -----------------------------------------------------------


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get database session from app state."""
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session


def get_graph_service(request: Request) -> KnowledgeGraphService:
    """Get the knowledge graph service from app state."""
    driver = request.app.state.neo4j_driver
    return KnowledgeGraphService(driver)


def get_embedding_service() -> EmbeddingService:
    """Get the embedding service."""
    return EmbeddingService()


def get_builder(request: Request) -> KnowledgeGraphBuilder:
    """Get the knowledge graph builder."""
    graph_service = get_graph_service(request)
    embedding_service = get_embedding_service()
    return KnowledgeGraphBuilder(graph_service, embedding_service)


# -- Routes -------------------------------------------------------------------


@router.post("/build", response_model=BuildResponse, status_code=status.HTTP_202_ACCEPTED)
async def build_graph(
    payload: BuildRequest,
    session: AsyncSession = Depends(get_session),
    builder: KnowledgeGraphBuilder = Depends(get_builder),
) -> dict[str, Any]:
    """Trigger knowledge graph construction for an engagement.

    This builds the graph by:
    1. Fetching validated evidence fragments
    2. Extracting entities from each fragment
    3. Resolving entities across fragments
    4. Creating nodes and relationships in Neo4j
    5. Generating and storing embeddings

    Set incremental=True to only process new fragments.
    """
    try:
        result = await builder.build_knowledge_graph(
            session=session,
            engagement_id=str(payload.engagement_id),
            incremental=payload.incremental,
        )
        return {
            "engagement_id": result.engagement_id,
            "node_count": result.node_count,
            "relationship_count": result.relationship_count,
            "nodes_by_label": result.nodes_by_label,
            "relationships_by_type": result.relationships_by_type,
            "fragments_processed": result.fragments_processed,
            "entities_extracted": result.entities_extracted,
            "entities_resolved": result.entities_resolved,
            "errors": result.errors,
        }
    except Exception as e:
        logger.exception("Graph build failed for engagement %s", payload.engagement_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph build failed: {e}",
        ) from e


@router.post("/query")
async def execute_query(
    payload: CypherQueryRequest,
    graph_service: KnowledgeGraphService = Depends(get_graph_service),
) -> list[dict[str, Any]]:
    """Execute a read-only Cypher query against the knowledge graph.

    Only read operations (MATCH, RETURN) are allowed.
    Parameters should be used for all variable values to prevent injection.
    """
    # Basic write-protection: reject mutations
    query_upper = payload.query.upper().strip()
    write_keywords = ["CREATE", "DELETE", "DETACH", "SET", "REMOVE", "MERGE", "DROP"]
    for keyword in write_keywords:
        if keyword in query_upper:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Write operations ({keyword}) are not allowed via the query endpoint",
            )

    try:
        results = await graph_service._run_query(payload.query, payload.parameters)
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Query execution failed: {e}",
        ) from e


@router.get("/traverse/{node_id}", response_model=list[NodeResponse])
async def traverse_graph(
    node_id: str,
    depth: int = 2,
    relationship_types: str | None = None,
    graph_service: KnowledgeGraphService = Depends(get_graph_service),
) -> list[dict[str, Any]]:
    """Traverse the knowledge graph from a starting node.

    Query parameters:
    - depth: Maximum traversal depth (1-5, default 2)
    - relationship_types: Comma-separated list of relationship types to follow
    """
    if depth < 1 or depth > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Depth must be between 1 and 5",
        )

    rel_types = None
    if relationship_types:
        rel_types = [rt.strip() for rt in relationship_types.split(",")]

    nodes = await graph_service.traverse(
        start_id=node_id,
        depth=depth,
        relationship_types=rel_types,
    )

    return [
        {
            "id": node.id,
            "label": node.label,
            "properties": node.properties,
        }
        for node in nodes
    ]


@router.get("/search", response_model=list[SearchResult])
async def semantic_search(
    query: str,
    top_k: int = 10,
    engagement_id: UUID | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Search the knowledge graph using semantic similarity.

    Generates an embedding for the query text and finds the most
    similar evidence fragments using pgvector cosine distance.

    Query parameters:
    - query: The text to search for
    - top_k: Number of results (1-100, default 10)
    - engagement_id: Optional engagement scope
    """
    if top_k < 1 or top_k > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="top_k must be between 1 and 100",
        )

    embedding_service = get_embedding_service()
    eng_id = str(engagement_id) if engagement_id else None

    results = await embedding_service.search_by_text(
        session=session,
        query_text=query,
        engagement_id=eng_id,
        top_k=top_k,
    )
    return results


@router.get("/{engagement_id}/stats", response_model=StatsResponse)
async def get_graph_stats(
    engagement_id: UUID,
    graph_service: KnowledgeGraphService = Depends(get_graph_service),
) -> dict[str, Any]:
    """Get statistics for an engagement's knowledge graph.

    Returns node and relationship counts broken down by type.
    """
    stats = await graph_service.get_stats(str(engagement_id))
    return {
        "node_count": stats.node_count,
        "relationship_count": stats.relationship_count,
        "nodes_by_label": stats.nodes_by_label,
        "relationships_by_type": stats.relationships_by_type,
    }


@router.get("/{engagement_id}/subgraph", response_model=SubgraphResponse)
async def get_engagement_subgraph(
    engagement_id: UUID,
    graph_service: KnowledgeGraphService = Depends(get_graph_service),
) -> dict[str, Any]:
    """Get the full knowledge graph for an engagement as JSON.

    Returns all nodes and relationships scoped to the engagement.
    """
    subgraph = await graph_service.get_engagement_subgraph(str(engagement_id))
    return {
        "nodes": [
            {
                "id": node.id,
                "label": node.label,
                "properties": node.properties,
            }
            for node in subgraph["nodes"]
        ],
        "relationships": [
            {
                "id": rel.id,
                "from_id": rel.from_id,
                "to_id": rel.to_id,
                "relationship_type": rel.relationship_type,
                "properties": rel.properties,
            }
            for rel in subgraph["relationships"]
        ],
    }
