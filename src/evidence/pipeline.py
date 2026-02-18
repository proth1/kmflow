"""Evidence processing pipeline.

Orchestrates the upload -> classify -> parse -> fragment -> store workflow
for evidence files. After fragment extraction, the intelligence pipeline
activates: entity extraction, knowledge graph building, embedding generation,
and semantic bridge execution.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from neo4j import AsyncDriver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    AuditAction,
    AuditLog,
    EvidenceCategory,
    EvidenceFragment,
    EvidenceItem,
)
from src.evidence.parsers.base import ParseResult
from src.evidence.parsers.factory import classify_by_extension, detect_format, parse_file

logger = logging.getLogger(__name__)

# Default storage directory (relative to project root)
DEFAULT_EVIDENCE_STORE = "evidence_store"


def compute_content_hash(file_content: bytes) -> str:
    """Compute SHA-256 hash of file content for integrity verification.

    Args:
        file_content: The raw bytes of the file.

    Returns:
        Hex-encoded SHA-256 hash string (64 characters).
    """
    return hashlib.sha256(file_content).hexdigest()


async def check_duplicate(session: AsyncSession, content_hash: str, engagement_id: uuid.UUID) -> uuid.UUID | None:
    """Check if a file with the same hash already exists in the engagement.

    Args:
        session: Database session.
        content_hash: SHA-256 hash of the file content.
        engagement_id: The engagement to check within.

    Returns:
        The UUID of the existing evidence item if a duplicate is found, else None.
    """
    result = await session.execute(
        select(EvidenceItem.id).where(
            EvidenceItem.engagement_id == engagement_id,
            EvidenceItem.content_hash == content_hash,
        )
    )
    existing = result.scalar_one_or_none()
    return existing


async def store_file(
    file_content: bytes,
    file_name: str,
    engagement_id: uuid.UUID,
    evidence_store: str = DEFAULT_EVIDENCE_STORE,
    storage_backend: Any | None = None,
) -> tuple[str, dict[str, Any]]:
    """Store an uploaded file using the configured storage backend.

    When a ``StorageBackend`` is provided, delegates to it for ACID
    writes (Delta Lake) or future backends. Falls back to direct
    filesystem writes for backward compatibility.

    Args:
        file_content: The raw bytes of the file.
        file_name: Original filename.
        engagement_id: The engagement this evidence belongs to.
        evidence_store: Base directory for evidence storage (legacy).
        storage_backend: Optional StorageBackend instance.

    Returns:
        Tuple of (file_path, storage_metadata_dict).
    """
    if storage_backend is not None:
        from src.datalake.backend import StorageBackend

        if isinstance(storage_backend, StorageBackend):
            result = await storage_backend.write(
                engagement_id=str(engagement_id),
                file_name=file_name,
                content=file_content,
            )
            return result.path, {
                "storage_version": result.version,
                "content_hash": result.content_hash,
                **result.extra,
            }
        raise TypeError(
            f"storage_backend must implement StorageBackend protocol, "
            f"got {type(storage_backend).__name__}"
        )

    # Legacy local filesystem fallback
    engagement_dir = Path(evidence_store) / str(engagement_id)
    engagement_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f"{uuid.uuid4().hex[:8]}_{file_name}"
    file_path = engagement_dir / unique_name

    with open(file_path, "wb") as f:
        f.write(file_content)

    return str(file_path), {}


async def process_evidence(
    session: AsyncSession,
    evidence_item: EvidenceItem,
) -> list[EvidenceFragment]:
    """Run the parsing pipeline on an evidence item.

    Parses the file, creates fragments, and stores them in the database.

    Args:
        session: Database session.
        evidence_item: The evidence item to process (must have file_path set).

    Returns:
        List of created EvidenceFragment records.
    """
    if not evidence_item.file_path or not os.path.exists(evidence_item.file_path):
        logger.warning("Evidence item %s has no valid file path", evidence_item.id)
        return []

    # Parse the file
    parse_result: ParseResult = await parse_file(evidence_item.file_path, evidence_item.name)

    if parse_result.error:
        logger.warning("Parse error for %s: %s", evidence_item.name, parse_result.error)

    # Create fragment records
    fragments: list[EvidenceFragment] = []
    for parsed_frag in parse_result.fragments:
        fragment = EvidenceFragment(
            evidence_id=evidence_item.id,
            fragment_type=parsed_frag.fragment_type,
            content=parsed_frag.content,
            metadata_json=json.dumps(parsed_frag.metadata) if parsed_frag.metadata else None,
        )
        session.add(fragment)
        fragments.append(fragment)

    return fragments


# ---------------------------------------------------------------------------
# Intelligence pipeline steps (S78, S79, S80)
# ---------------------------------------------------------------------------


async def extract_fragment_entities(
    fragments: list[EvidenceFragment],
    engagement_id: str,
) -> list[dict[str, Any]]:
    """Run entity extraction on fragments and store entities as metadata.

    Args:
        fragments: List of EvidenceFragment records with content.
        engagement_id: The engagement ID for scoping.

    Returns:
        List of extraction results with entity data per fragment.
    """
    from src.semantic.entity_extraction import extract_entities, resolve_entities

    all_results: list[dict[str, Any]] = []
    all_entities = []

    for fragment in fragments:
        if not fragment.content:
            continue

        result = await extract_entities(
            text=fragment.content,
            fragment_id=str(fragment.id) if fragment.id else None,
        )

        if result.entities:
            # Store entities as fragment metadata
            entity_data = [
                {
                    "id": e.id,
                    "type": e.entity_type,
                    "name": e.name,
                    "confidence": e.confidence,
                }
                for e in result.entities
            ]

            existing_meta = {}
            if fragment.metadata_json:
                try:
                    existing_meta = json.loads(fragment.metadata_json) if isinstance(fragment.metadata_json, str) else fragment.metadata_json
                except (json.JSONDecodeError, TypeError):
                    existing_meta = {}

            existing_meta["entities"] = entity_data
            existing_meta["entity_count"] = len(result.entities)
            fragment.metadata_json = json.dumps(existing_meta)

            all_entities.extend(result.entities)

        all_results.append({
            "fragment_id": str(fragment.id) if fragment.id else None,
            "entity_count": len(result.entities),
            "entities": result.entities,
        })

    # Resolve entities across all fragments
    resolved = resolve_entities(all_entities) if all_entities else []

    logger.info(
        "Entity extraction for engagement %s: %d entities extracted, %d resolved",
        engagement_id,
        len(all_entities),
        len(resolved),
    )

    return all_results


async def build_fragment_graph(
    fragments: list[EvidenceFragment],
    engagement_id: str,
    neo4j_driver: AsyncDriver | None = None,
) -> dict[str, Any]:
    """Create knowledge graph nodes from extracted entities.

    Args:
        fragments: Fragments with entity metadata.
        engagement_id: Engagement ID for scoping.
        neo4j_driver: Neo4j async driver instance.

    Returns:
        Dict with node_count, relationship_count, errors.
    """
    if not neo4j_driver:
        logger.debug("No Neo4j driver available, skipping graph build")
        return {"node_count": 0, "relationship_count": 0, "errors": []}

    from src.semantic.entity_extraction import EntityType, ExtractedEntity, resolve_entities
    from src.semantic.graph import KnowledgeGraphService
    from src.semantic.ontology.loader import get_entity_type_to_label

    graph_service = KnowledgeGraphService(neo4j_driver)

    # Map entity types to Neo4j labels (loaded from ontology YAML)
    type_to_label = get_entity_type_to_label()

    # Collect all entities from fragment metadata
    all_entities: list[ExtractedEntity] = []
    entity_evidence_map: dict[str, list[str]] = {}

    for fragment in fragments:
        if not fragment.metadata_json:
            continue

        try:
            meta = json.loads(fragment.metadata_json) if isinstance(fragment.metadata_json, str) else fragment.metadata_json
        except (json.JSONDecodeError, TypeError):
            continue

        entity_data = meta.get("entities", [])
        evidence_id = str(fragment.evidence_id) if fragment.evidence_id else ""

        for ed in entity_data:
            entity = ExtractedEntity(
                id=ed["id"],
                entity_type=EntityType(ed["type"]),
                name=ed["name"],
                confidence=ed["confidence"],
            )
            all_entities.append(entity)
            if entity.id not in entity_evidence_map:
                entity_evidence_map[entity.id] = []
            if evidence_id and evidence_id not in entity_evidence_map[entity.id]:
                entity_evidence_map[entity.id].append(evidence_id)

    if not all_entities:
        return {"node_count": 0, "relationship_count": 0, "errors": []}

    resolved = resolve_entities(all_entities)
    node_count = 0
    relationship_count = 0
    errors: list[str] = []

    # Batch create nodes
    entity_to_node: dict[str, str] = {}
    for entity in resolved:
        label = type_to_label.get(entity.entity_type)
        if not label:
            continue
        try:
            node = await graph_service.create_node(
                label,
                {
                    "id": entity.id,
                    "name": entity.name,
                    "engagement_id": engagement_id,
                    "confidence": entity.confidence,
                    "entity_type": entity.entity_type,
                },
            )
            entity_to_node[entity.id] = node.id
            node_count += 1
        except Exception as e:
            errors.append(f"Node creation failed for {entity.name}: {e}")

    # Create CO_OCCURS_WITH relationships for entities from same evidence
    evidence_to_entities: dict[str, set[str]] = {}
    for eid, ev_ids in entity_evidence_map.items():
        for ev_id in ev_ids:
            if ev_id not in evidence_to_entities:
                evidence_to_entities[ev_id] = set()
            evidence_to_entities[ev_id].add(eid)

    created_pairs: set[tuple[str, str]] = set()
    for ev_id, entity_ids in evidence_to_entities.items():
        entity_list = sorted(entity_ids)
        for i, eid_a in enumerate(entity_list):
            for eid_b in entity_list[i + 1 :]:
                pair = (eid_a, eid_b)
                if pair in created_pairs:
                    continue
                created_pairs.add(pair)

                node_a = entity_to_node.get(eid_a)
                node_b = entity_to_node.get(eid_b)
                if not node_a or not node_b:
                    continue
                try:
                    await graph_service.create_relationship(
                        from_id=node_a,
                        to_id=node_b,
                        relationship_type="CO_OCCURS_WITH",
                        properties={"evidence_id": ev_id},
                    )
                    relationship_count += 1
                except Exception as e:
                    errors.append(f"Relationship failed {node_a}->{node_b}: {e}")

    logger.info(
        "Graph build for engagement %s: %d nodes, %d relationships",
        engagement_id,
        node_count,
        relationship_count,
    )

    return {"node_count": node_count, "relationship_count": relationship_count, "errors": errors}


async def generate_fragment_embeddings(
    session: AsyncSession,
    fragments: list[EvidenceFragment],
) -> int:
    """Generate and store embeddings for evidence fragments.

    Args:
        session: Database session for pgvector storage.
        fragments: Fragments to generate embeddings for.

    Returns:
        Number of embeddings successfully generated and stored.
    """
    from src.rag.embeddings import EmbeddingService
    from src.semantic.embeddings import EmbeddingService as SemanticEmbeddingService

    if not fragments:
        return 0

    rag_service = EmbeddingService()
    semantic_service = SemanticEmbeddingService()

    # Collect texts for batch embedding
    texts: list[str] = []
    valid_fragments: list[EvidenceFragment] = []
    for frag in fragments:
        if frag.content and frag.content.strip():
            texts.append(frag.content)
            valid_fragments.append(frag)

    if not texts:
        return 0

    # Generate embeddings in batches
    embeddings = rag_service.generate_embeddings(texts, batch_size=32)

    # Store embeddings
    stored = 0
    for frag, embedding in zip(valid_fragments, embeddings, strict=True):
        try:
            await semantic_service.store_embedding(session, str(frag.id), embedding)
            stored += 1
        except Exception as e:
            logger.warning("Failed to store embedding for fragment %s: %s", frag.id, e)

    logger.info("Generated and stored %d/%d embeddings", stored, len(texts))
    return stored


async def run_semantic_bridges(
    engagement_id: str,
    neo4j_driver: AsyncDriver | None = None,
) -> dict[str, Any]:
    """Run all semantic bridges for an engagement.

    Executes ProcessEvidence, EvidencePolicy, ProcessTOM, and
    CommunicationDeviation bridges to create semantic relationships.

    Args:
        engagement_id: The engagement to run bridges for.
        neo4j_driver: Neo4j async driver instance.

    Returns:
        Dict with total relationships created and any errors.
    """
    if not neo4j_driver:
        logger.debug("No Neo4j driver available, skipping semantic bridges")
        return {"relationships_created": 0, "errors": []}

    from src.semantic.bridges.communication_deviation import CommunicationDeviationBridge
    from src.semantic.bridges.evidence_policy import EvidencePolicyBridge
    from src.semantic.bridges.process_evidence import ProcessEvidenceBridge
    from src.semantic.bridges.process_tom import ProcessTOMBridge
    from src.semantic.graph import KnowledgeGraphService

    graph_service = KnowledgeGraphService(neo4j_driver)

    bridges = [
        ("ProcessEvidence", ProcessEvidenceBridge(graph_service)),
        ("EvidencePolicy", EvidencePolicyBridge(graph_service)),
        ("ProcessTOM", ProcessTOMBridge(graph_service)),
        ("CommunicationDeviation", CommunicationDeviationBridge(graph_service)),
    ]

    total_created = 0
    all_errors: list[str] = []

    for name, bridge in bridges:
        try:
            result = await bridge.run(engagement_id)
            total_created += result.relationships_created
            all_errors.extend(result.errors)
            logger.info("Bridge %s: %d relationships created", name, result.relationships_created)
        except Exception as e:
            error_msg = f"Bridge {name} failed: {e}"
            all_errors.append(error_msg)
            logger.warning(error_msg)

    logger.info(
        "Semantic bridges for engagement %s: %d relationships, %d errors",
        engagement_id,
        total_created,
        len(all_errors),
    )

    return {"relationships_created": total_created, "errors": all_errors}


async def run_intelligence_pipeline(
    session: AsyncSession,
    fragments: list[EvidenceFragment],
    engagement_id: str,
    neo4j_driver: AsyncDriver | None = None,
) -> dict[str, Any]:
    """Run the full intelligence pipeline on extracted fragments.

    Steps:
    1. Entity extraction (S78)
    2. Knowledge graph building (S79)
    3. Embedding generation (S80)
    4. Semantic bridge execution (S81-S84)

    Args:
        session: Database session.
        fragments: Extracted evidence fragments.
        engagement_id: The engagement these fragments belong to.
        neo4j_driver: Neo4j driver for graph operations (optional).

    Returns:
        Dict with intelligence pipeline results.
    """
    results: dict[str, Any] = {
        "entities_extracted": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
        "embeddings_stored": 0,
        "bridge_relationships": 0,
        "errors": [],
    }

    if not fragments:
        return results

    # Step 1: Entity extraction
    try:
        extraction_results = await extract_fragment_entities(
            fragments, str(engagement_id)
        )
        results["entities_extracted"] = sum(r["entity_count"] for r in extraction_results)
    except Exception as e:
        logger.warning("Entity extraction failed: %s", e)
        results["errors"].append(f"Entity extraction: {e}")

    # Step 2: Knowledge graph building
    try:
        graph_results = await build_fragment_graph(
            fragments, str(engagement_id), neo4j_driver
        )
        results["graph_nodes"] = graph_results["node_count"]
        results["graph_relationships"] = graph_results["relationship_count"]
        results["errors"].extend(graph_results.get("errors", []))
    except Exception as e:
        logger.warning("Graph building failed: %s", e)
        results["errors"].append(f"Graph building: {e}")

    # Step 3: Embedding generation
    try:
        results["embeddings_stored"] = await generate_fragment_embeddings(
            session, fragments
        )
    except Exception as e:
        logger.warning("Embedding generation failed: %s", e)
        results["errors"].append(f"Embedding generation: {e}")

    # Step 4: Semantic bridges
    try:
        bridge_results = await run_semantic_bridges(
            str(engagement_id), neo4j_driver
        )
        results["bridge_relationships"] = bridge_results["relationships_created"]
        results["errors"].extend(bridge_results.get("errors", []))
    except Exception as e:
        logger.warning("Semantic bridges failed: %s", e)
        results["errors"].append(f"Semantic bridges: {e}")

    logger.info(
        "Intelligence pipeline for engagement %s: %d entities, %d nodes, %d embeddings, %d bridge rels",
        engagement_id,
        results["entities_extracted"],
        results["graph_nodes"],
        results["embeddings_stored"],
        results["bridge_relationships"],
    )

    return results


async def ingest_evidence(
    session: AsyncSession,
    engagement_id: uuid.UUID,
    file_content: bytes,
    file_name: str,
    category: EvidenceCategory | None = None,
    metadata: dict | None = None,
    mime_type: str | None = None,
    evidence_store: str = DEFAULT_EVIDENCE_STORE,
    neo4j_driver: AsyncDriver | None = None,
    storage_backend: Any | None = None,
) -> tuple[EvidenceItem, list[EvidenceFragment], uuid.UUID | None]:
    """Full evidence ingestion pipeline: upload -> classify -> parse -> store -> intelligence.

    This is the main entry point for evidence ingestion. After basic parsing,
    the intelligence pipeline runs: entity extraction, graph building, and
    embedding generation.

    Args:
        session: Database session.
        engagement_id: The engagement to attach evidence to.
        file_content: Raw file bytes.
        file_name: Original filename.
        category: Evidence category (auto-detected if not provided).
        metadata: Additional metadata JSON.
        mime_type: MIME type of the file.
        evidence_store: Base directory for file storage.
        neo4j_driver: Neo4j driver for intelligence pipeline (optional).
        storage_backend: Optional StorageBackend for Delta Lake / custom storage.

    Returns:
        Tuple of (evidence_item, fragments, duplicate_of_id).
        duplicate_of_id is set if the file is a duplicate.
    """
    # Step 1: Compute content hash
    content_hash = compute_content_hash(file_content)

    # Step 2: Check for duplicates
    duplicate_of_id = await check_duplicate(session, content_hash, engagement_id)

    # Step 3: Auto-classify if category not provided
    if category is None:
        detected = classify_by_extension(file_name)
        category = EvidenceCategory(detected) if detected else EvidenceCategory.DOCUMENTS

    # Step 4: Detect format
    file_format = detect_format(file_name)

    # Step 5: Store file (via storage backend if provided)
    file_path, storage_meta = await store_file(
        file_content, file_name, engagement_id, evidence_store, storage_backend
    )

    # Step 6: Create evidence item
    delta_path = storage_meta.get("delta_table") if storage_meta else None
    evidence_item = EvidenceItem(
        engagement_id=engagement_id,
        name=file_name,
        category=category,
        format=file_format,
        content_hash=content_hash,
        file_path=file_path,
        size_bytes=len(file_content),
        mime_type=mime_type,
        metadata_json=metadata,
        duplicate_of_id=duplicate_of_id,
        delta_path=delta_path,
    )
    session.add(evidence_item)
    await session.flush()

    # Step 7: Parse and create fragments
    fragments = await process_evidence(session, evidence_item)

    # Step 8: Intelligence pipeline (entity extraction, graph, embeddings)
    if fragments:
        await session.flush()  # Ensure fragment IDs are assigned
        try:
            await run_intelligence_pipeline(
                session=session,
                fragments=fragments,
                engagement_id=str(engagement_id),
                neo4j_driver=neo4j_driver,
            )
        except Exception as e:
            logger.warning("Intelligence pipeline failed (non-fatal): %s", e)

    # Step 9: Audit log
    audit = AuditLog(
        engagement_id=engagement_id,
        action=AuditAction.EVIDENCE_UPLOADED,
        details=json.dumps(
            {
                "evidence_id": str(evidence_item.id),
                "file_name": file_name,
                "category": str(category),
                "content_hash": content_hash,
                "is_duplicate": duplicate_of_id is not None,
            }
        ),
    )
    session.add(audit)

    return evidence_item, fragments, duplicate_of_id
