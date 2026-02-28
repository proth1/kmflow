"""Knowledge graph construction pipeline.

Orchestrates the full graph building workflow:
1. Fetch validated evidence fragments for an engagement
2. Generate and store embeddings for all fragments
3. Run entity extraction on each fragment
4. Resolve entities across fragments (dedup)
5. Create nodes in Neo4j
6. Create relationships based on co-occurrence and semantic similarity
7. Create SUPPORTED_BY edges from entities to evidence items
8. Return graph statistics

Supports incremental mode: add new evidence without rebuilding the graph.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from neo4j.exceptions import Neo4jError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import EvidenceFragment, EvidenceItem, ValidationStatus
from src.semantic.embeddings import EmbeddingService
from src.semantic.entity_extraction import (
    EntityType,
    ExtractedEntity,
    extract_entities,
    resolve_entities,
)
from src.semantic.graph import KnowledgeGraphService
from src.semantic.ontology.loader import get_entity_type_to_label

logger = logging.getLogger(__name__)

# Map entity types to Neo4j node labels (loaded from ontology YAML)
_ENTITY_TYPE_TO_LABEL: dict[str, str] = get_entity_type_to_label()


@dataclass
class BuildResult:
    """Result from a graph build operation.

    Attributes:
        engagement_id: The engagement this build was for.
        node_count: Number of nodes created.
        relationship_count: Number of relationships created.
        nodes_by_label: Breakdown of nodes by label.
        relationships_by_type: Breakdown of relationships by type.
        fragments_processed: Number of fragments processed.
        entities_extracted: Total entities extracted before resolution.
        entities_resolved: Total entities after resolution.
        errors: List of error messages for partial failures.
    """

    engagement_id: str = ""
    node_count: int = 0
    relationship_count: int = 0
    nodes_by_label: dict[str, int] = field(default_factory=dict)
    relationships_by_type: dict[str, int] = field(default_factory=dict)
    fragments_processed: int = 0
    entities_extracted: int = 0
    entities_resolved: int = 0
    errors: list[str] = field(default_factory=list)


class KnowledgeGraphBuilder:
    """Orchestrates knowledge graph construction from evidence fragments.

    Coordinates entity extraction, resolution, and graph creation
    for a given engagement.
    """

    def __init__(
        self,
        graph_service: KnowledgeGraphService,
        embedding_service: EmbeddingService,
    ) -> None:
        """Initialize the builder with graph and embedding services.

        Args:
            graph_service: Service for Neo4j graph operations.
            embedding_service: Service for generating embeddings.
        """
        self._graph = graph_service
        self._embeddings = embedding_service

    async def _fetch_fragments(
        self,
        session: AsyncSession,
        engagement_id: str,
        only_new: bool = False,
    ) -> list[tuple[str, str, str]]:
        """Fetch validated evidence fragments for an engagement.

        Args:
            session: Database session.
            engagement_id: Engagement to fetch fragments for.
            only_new: If True, only fetch fragments without embeddings (incremental).

        Returns:
            List of (fragment_id, content, evidence_id) tuples.
        """
        query = (
            select(
                EvidenceFragment.id,
                EvidenceFragment.content,
                EvidenceFragment.evidence_id,
            )
            .join(EvidenceItem, EvidenceFragment.evidence_id == EvidenceItem.id)
            .where(EvidenceItem.engagement_id == engagement_id)
            .where(
                EvidenceItem.validation_status.in_(
                    [
                        ValidationStatus.VALIDATED,
                        ValidationStatus.ACTIVE,
                    ]
                )
            )
        )

        if only_new:
            query = query.where(EvidenceFragment.embedding.is_(None))

        result = await session.execute(query)
        rows = result.all()
        return [(str(row[0]), row[1], str(row[2])) for row in rows]

    async def _extract_all_entities(
        self,
        fragments: list[tuple[str, str, str]],
    ) -> tuple[list[ExtractedEntity], dict[str, list[str]]]:
        """Run entity extraction on all fragments concurrently.

        Uses asyncio.gather with a semaphore (max 10 concurrent) instead of
        sequential awaiting to reduce total extraction time.

        Args:
            fragments: List of (fragment_id, content, evidence_id) tuples.

        Returns:
            Tuple of (all_entities, entity_to_evidence_map).
            entity_to_evidence_map maps entity IDs to evidence item IDs.
        """
        sem = asyncio.Semaphore(10)

        async def _extract_with_sem(fragment_id: str, content: str):
            async with sem:
                return await extract_entities(content, fragment_id=fragment_id)

        tasks = [_extract_with_sem(fragment_id, content) for fragment_id, content, _ in fragments]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        all_entities: list[ExtractedEntity] = []
        entity_evidence_map: dict[str, list[str]] = {}

        for (fragment_id, _content, evidence_id), result in zip(fragments, raw_results, strict=False):
            if isinstance(result, Exception):
                logger.warning("Entity extraction failed for fragment %s: %s", fragment_id, result)
                continue
            for entity in result.entities:
                all_entities.append(entity)
                if entity.id not in entity_evidence_map:
                    entity_evidence_map[entity.id] = []
                if evidence_id not in entity_evidence_map[entity.id]:
                    entity_evidence_map[entity.id].append(evidence_id)

        return all_entities, entity_evidence_map

    async def _create_nodes(
        self,
        entities: list[ExtractedEntity],
        engagement_id: str,
    ) -> dict[str, str]:
        """Create Neo4j nodes for resolved entities.

        Groups entities by label and batch-creates them using UNWIND to
        avoid N+1 round-trips to Neo4j.

        Args:
            entities: List of resolved entities to create nodes for.
            engagement_id: Engagement ID for scoping.

        Returns:
            Dict mapping entity ID to created node ID.
        """
        entity_to_node: dict[str, str] = {}

        # Bucket entities by their Neo4j label so we can batch per label
        nodes_by_label: dict[str, list[dict]] = defaultdict(list)
        # Preserve the entity.id -> props["id"] mapping for the return value
        entity_id_to_node_id: dict[str, str] = {}

        for entity in entities:
            label = _ENTITY_TYPE_TO_LABEL.get(entity.entity_type)
            if not label:
                continue

            node_id = str(uuid.uuid4())
            props: dict = {
                "id": node_id,
                "name": entity.name,
                "engagement_id": engagement_id,
                "confidence": entity.confidence,
                "entity_type": entity.entity_type,
            }
            if entity.aliases:
                props["aliases"] = ",".join(entity.aliases)

            nodes_by_label[label].append(props)
            entity_id_to_node_id[entity.id] = node_id

        # Batch create per label — one Cypher round-trip per distinct label
        for label, props_list in nodes_by_label.items():
            try:
                await self._graph.batch_create_nodes(label, props_list)
                for props in props_list:
                    # Find the entity whose node_id matches and record the mapping
                    entity_to_node[props["id"]] = props["id"]
            except Neo4jError as e:
                logger.warning("Failed to batch-create nodes for label %s: %s", label, e)

        # Build the entity.id -> node_id mapping for callers
        result: dict[str, str] = {}
        for entity in entities:
            node_id = entity_id_to_node_id.get(entity.id)
            if node_id and node_id in entity_to_node:
                result[entity.id] = node_id

        return result

    async def _create_evidence_links(
        self,
        entity_to_node: dict[str, str],
        entity_evidence_map: dict[str, list[str]],
        engagement_id: str,
    ) -> int:
        """Create SUPPORTED_BY relationships from entities to evidence items.

        Batches Evidence node upserts and SUPPORTED_BY edge creation to avoid
        N+1 round-trips. Evidence nodes for distinct evidence IDs are collected
        first; those that don't yet exist are batch-created; then all edges are
        written in a single UNWIND query.

        Args:
            entity_to_node: Mapping from entity ID to node ID.
            entity_evidence_map: Mapping from entity ID to evidence item IDs.
            engagement_id: Engagement ID for scoping.

        Returns:
            Number of relationships created.
        """
        # Collect every (node_id, ev_node_id) pair we need to link
        pairs: list[tuple[str, str]] = []
        evidence_props: dict[str, dict] = {}

        for entity_id, evidence_ids in entity_evidence_map.items():
            node_id = entity_to_node.get(entity_id)
            if not node_id:
                continue
            for evidence_id in evidence_ids:
                ev_node_id = f"ev-{evidence_id}"
                pairs.append((node_id, ev_node_id))
                if ev_node_id not in evidence_props:
                    evidence_props[ev_node_id] = {
                        "id": ev_node_id,
                        "name": f"Evidence {evidence_id}",
                        "engagement_id": engagement_id,
                        "evidence_item_id": evidence_id,
                    }

        if not pairs:
            return 0

        # Batch-upsert Evidence nodes (MERGE avoids duplicates without pre-check)
        if evidence_props:
            try:
                await self._graph.batch_create_nodes("Evidence", list(evidence_props.values()))
            except Neo4jError as e:
                logger.warning("Failed to batch-create Evidence nodes: %s", e)

        # Batch-create all SUPPORTED_BY edges in one UNWIND round-trip
        rels = [
            {"from_id": node_id, "to_id": ev_node_id, "properties": {"source": "extraction"}}
            for node_id, ev_node_id in pairs
        ]
        try:
            count = await self._graph.batch_create_relationships("SUPPORTED_BY", rels)
        except Neo4jError as e:
            logger.warning("Failed to batch-create SUPPORTED_BY relationships: %s", e)
            count = 0

        return count

    async def _create_co_occurrence_relationships(
        self,
        entities: list[ExtractedEntity],
        entity_evidence_map: dict[str, list[str]],
        entity_to_node: dict[str, str],
    ) -> int:
        """Create CO_OCCURS_WITH relationships between entities from same evidence.

        Entities that were extracted from the same evidence item are
        connected with CO_OCCURS_WITH edges.

        Args:
            entities: List of resolved entities.
            entity_evidence_map: Mapping from entity ID to evidence item IDs.
            entity_to_node: Mapping from entity ID to node ID.

        Returns:
            Number of relationships created.
        """
        # Build reverse map: evidence_id -> set of entity_ids
        evidence_to_entities: dict[str, set[str]] = {}
        for entity_id, ev_ids in entity_evidence_map.items():
            for ev_id in ev_ids:
                if ev_id not in evidence_to_entities:
                    evidence_to_entities[ev_id] = set()
                evidence_to_entities[ev_id].add(entity_id)

        # Build deduplicated list of CO_OCCURS_WITH edges across all evidence
        created_pairs: set[tuple[str, str]] = set()
        rels: list[dict] = []

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

                    rels.append(
                        {
                            "from_id": node_a,
                            "to_id": node_b,
                            "properties": {"evidence_id": ev_id},
                        }
                    )

        if not rels:
            return 0

        try:
            count = await self._graph.batch_create_relationships("CO_OCCURS_WITH", rels)
        except Neo4jError as e:
            logger.warning("Failed to batch-create CO_OCCURS_WITH relationships: %s", e)
            count = 0

        return count

    async def _create_semantic_relationships(
        self,
        entities: list[ExtractedEntity],
        entity_to_node: dict[str, str],
    ) -> int:
        """Create FOLLOWED_BY and USES relationships based on entity types.

        Heuristic rules:
        - Activity -> Role = OWNED_BY (role performs activity)
        - Activity -> System = USES (activity uses system)
        - Activity -> Activity = FOLLOWED_BY (sequential activities)
        - Decision -> Activity = REQUIRES (decision requires activity)

        Args:
            entities: List of resolved entities.
            entity_to_node: Mapping from entity ID to node ID.

        Returns:
            Number of relationships created.
        """
        # Group entities by type for cross-type relationships
        by_type: dict[str, list[ExtractedEntity]] = {}
        for entity in entities:
            etype = entity.entity_type
            if etype not in by_type:
                by_type[etype] = []
            by_type[etype].append(entity)

        count = 0
        activities = by_type.get(EntityType.ACTIVITY, [])
        roles = by_type.get(EntityType.ROLE, [])
        systems = by_type.get(EntityType.SYSTEM, [])
        decisions = by_type.get(EntityType.DECISION, [])

        inferred_props = {"inferred": True}

        # Collect all inferred edges grouped by relationship type, then batch-create
        owned_by_rels = [
            {"from_id": entity_to_node[act.id], "to_id": entity_to_node[role.id], "properties": inferred_props}
            for act in activities
            for role in roles
            if entity_to_node.get(act.id) and entity_to_node.get(role.id)
        ]
        uses_rels = [
            {"from_id": entity_to_node[act.id], "to_id": entity_to_node[sys.id], "properties": inferred_props}
            for act in activities
            for sys in systems
            if entity_to_node.get(act.id) and entity_to_node.get(sys.id)
        ]
        requires_rels = [
            {"from_id": entity_to_node[dec.id], "to_id": entity_to_node[act.id], "properties": inferred_props}
            for dec in decisions
            for act in activities
            if entity_to_node.get(dec.id) and entity_to_node.get(act.id)
        ]

        for rel_type, rels in (
            ("OWNED_BY", owned_by_rels),
            ("USES", uses_rels),
            ("REQUIRES", requires_rels),
        ):
            if not rels:
                continue
            try:
                created = await self._graph.batch_create_relationships(rel_type, rels)
                count += created
            except Neo4jError as e:
                logger.debug("Batch relationship creation skipped for %s: %s", rel_type, e)

        return count

    _EMBEDDING_BATCH_SIZE = 100  # Max embeddings per DB round-trip (C3-H2)

    async def _generate_and_store_embeddings(
        self,
        session: AsyncSession,
        fragments: list[tuple[str, str, str]],
    ) -> tuple[int, list[str]]:
        """Generate and store embeddings for fragments.

        Generates embeddings individually (each may call the embedding model),
        then stores them in batches of _EMBEDDING_BATCH_SIZE to avoid N+1
        database writes (C3-H2).

        Args:
            session: Database session.
            fragments: List of (fragment_id, content, evidence_id) tuples.

        Returns:
            Tuple of (count of embeddings stored, list of error messages).
        """
        errors: list[str] = []
        pending: list[tuple[str, list[float]]] = []

        for fragment_id, content, _ in fragments:
            try:
                embedding = await self._embeddings.generate_embedding_async(content)
                pending.append((fragment_id, embedding))
            except (ValueError, RuntimeError) as e:
                msg = f"Embedding failed for fragment {fragment_id}: {e}"
                errors.append(msg)
                logger.warning("Failed to generate embedding for fragment %s: %s", fragment_id, e)

            # Flush batch when it reaches the size limit
            if len(pending) >= self._EMBEDDING_BATCH_SIZE:
                await self._embeddings.store_embeddings_batch(session, pending)
                pending = []

        # Flush any remaining embeddings
        if pending:
            await self._embeddings.store_embeddings_batch(session, pending)

        return len(fragments) - len(errors), errors

    async def build_knowledge_graph(
        self,
        session: AsyncSession,
        engagement_id: str,
        incremental: bool = False,
    ) -> BuildResult:
        """Build or incrementally update the knowledge graph for an engagement.

        Full pipeline:
        1. Fetch validated evidence fragments
        2. Generate and store embeddings (always, independent of entities)
        3. Run entity extraction on each fragment
        4. Resolve entities (dedup)
        5. Create nodes in Neo4j
        6. Create relationships (co-occurrence, semantic, evidence links)
        7. Return statistics

        Args:
            session: Database session.
            engagement_id: The engagement to build the graph for.
            incremental: If True, only process new fragments.

        Returns:
            BuildResult with statistics about the build.
        """
        result = BuildResult(engagement_id=engagement_id)

        # Step 1: Fetch fragments
        fragments = await self._fetch_fragments(session, engagement_id, only_new=incremental)
        result.fragments_processed = len(fragments)

        if not fragments:
            logger.info("No fragments to process for engagement %s", engagement_id)
            return result

        # Step 2: Generate and store embeddings (independent of entity extraction)
        _emb_count, emb_errors = await self._generate_and_store_embeddings(session, fragments)
        result.errors.extend(emb_errors)

        # Step 3: Extract entities
        all_entities, entity_evidence_map = await self._extract_all_entities(fragments)
        result.entities_extracted = len(all_entities)

        if not all_entities:
            logger.info("No entities extracted for engagement %s", engagement_id)
            return result

        # Step 4: Resolve entities
        resolved_entities, _ = resolve_entities(all_entities)
        result.entities_resolved = len(resolved_entities)

        # Step 5: Create nodes
        entity_to_node = await self._create_nodes(resolved_entities, engagement_id)
        result.node_count = len(entity_to_node)

        # Count nodes by label
        for entity in resolved_entities:
            label = _ENTITY_TYPE_TO_LABEL.get(entity.entity_type, "Unknown")
            if entity.id in entity_to_node:
                result.nodes_by_label[label] = result.nodes_by_label.get(label, 0) + 1

        # Step 6a: Create SUPPORTED_BY edges
        evidence_link_count = await self._create_evidence_links(entity_to_node, entity_evidence_map, engagement_id)
        result.relationships_by_type["SUPPORTED_BY"] = evidence_link_count

        # Step 6b: Create co-occurrence relationships
        co_occur_count = await self._create_co_occurrence_relationships(
            resolved_entities, entity_evidence_map, entity_to_node
        )
        result.relationships_by_type["CO_OCCURS_WITH"] = co_occur_count

        # Step 6c: Create semantic relationships
        semantic_count = await self._create_semantic_relationships(resolved_entities, entity_to_node)
        result.relationships_by_type["SEMANTIC_INFERRED"] = semantic_count

        result.relationship_count = evidence_link_count + co_occur_count + semantic_count

        logger.info(
            "Graph build complete for engagement %s: %d nodes, %d relationships",
            engagement_id,
            result.node_count,
            result.relationship_count,
        )

        return result
