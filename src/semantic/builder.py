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

import logging
from dataclasses import dataclass, field

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
        """Run entity extraction on all fragments.

        Args:
            fragments: List of (fragment_id, content, evidence_id) tuples.

        Returns:
            Tuple of (all_entities, entity_to_evidence_map).
            entity_to_evidence_map maps entity IDs to evidence item IDs.
        """
        all_entities: list[ExtractedEntity] = []
        # Track which entities came from which evidence items
        entity_evidence_map: dict[str, list[str]] = {}

        for fragment_id, content, evidence_id in fragments:
            result = await extract_entities(content, fragment_id=fragment_id)
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

        Args:
            entities: List of resolved entities to create nodes for.
            engagement_id: Engagement ID for scoping.

        Returns:
            Dict mapping entity ID to created node ID.
        """
        entity_to_node: dict[str, str] = {}
        nodes_by_label: dict[str, int] = {}

        for entity in entities:
            label = _ENTITY_TYPE_TO_LABEL.get(entity.entity_type)
            if not label:
                continue

            properties = {
                "id": entity.id,
                "name": entity.name,
                "engagement_id": engagement_id,
                "confidence": entity.confidence,
                "entity_type": entity.entity_type,
            }
            if entity.aliases:
                properties["aliases"] = ",".join(entity.aliases)

            try:
                node = await self._graph.create_node(label, properties)
                entity_to_node[entity.id] = node.id
                nodes_by_label[label] = nodes_by_label.get(label, 0) + 1
            except Exception as e:
                logger.warning("Failed to create node for entity %s: %s", entity.name, e)

        return entity_to_node

    async def _create_evidence_links(
        self,
        entity_to_node: dict[str, str],
        entity_evidence_map: dict[str, list[str]],
        engagement_id: str,
    ) -> int:
        """Create SUPPORTED_BY relationships from entities to evidence items.

        Args:
            entity_to_node: Mapping from entity ID to node ID.
            entity_evidence_map: Mapping from entity ID to evidence item IDs.
            engagement_id: Engagement ID for scoping.

        Returns:
            Number of relationships created.
        """
        count = 0
        for entity_id, evidence_ids in entity_evidence_map.items():
            node_id = entity_to_node.get(entity_id)
            if not node_id:
                continue

            for evidence_id in evidence_ids:
                # Create an Evidence node for the evidence item if needed
                ev_node_id = f"ev-{evidence_id}"
                try:
                    existing = await self._graph.get_node(ev_node_id)
                    if not existing:
                        await self._graph.create_node(
                            "Evidence",
                            {
                                "id": ev_node_id,
                                "name": f"Evidence {evidence_id}",
                                "engagement_id": engagement_id,
                                "evidence_item_id": evidence_id,
                            },
                        )

                    await self._graph.create_relationship(
                        from_id=node_id,
                        to_id=ev_node_id,
                        relationship_type="SUPPORTED_BY",
                        properties={"source": "extraction"},
                    )
                    count += 1
                except Exception as e:
                    logger.warning(
                        "Failed to create SUPPORTED_BY link %s -> %s: %s",
                        node_id,
                        evidence_id,
                        e,
                    )

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

        # Create CO_OCCURS_WITH for entity pairs from same evidence
        created_pairs: set[tuple[str, str]] = set()
        count = 0

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
                        await self._graph.create_relationship(
                            from_id=node_a,
                            to_id=node_b,
                            relationship_type="CO_OCCURS_WITH",
                            properties={"evidence_id": ev_id},
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(
                            "Failed to create CO_OCCURS_WITH %s -> %s: %s",
                            node_a,
                            node_b,
                            e,
                        )

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

        # Activity -> Role = OWNED_BY
        for activity in activities:
            for role in roles:
                act_node = entity_to_node.get(activity.id)
                role_node = entity_to_node.get(role.id)
                if act_node and role_node:
                    try:
                        await self._graph.create_relationship(
                            from_id=act_node,
                            to_id=role_node,
                            relationship_type="OWNED_BY",
                            properties={"inferred": True},
                        )
                        count += 1
                    except Exception:
                        pass

        # Activity -> System = USES
        for activity in activities:
            for system in systems:
                act_node = entity_to_node.get(activity.id)
                sys_node = entity_to_node.get(system.id)
                if act_node and sys_node:
                    try:
                        await self._graph.create_relationship(
                            from_id=act_node,
                            to_id=sys_node,
                            relationship_type="USES",
                            properties={"inferred": True},
                        )
                        count += 1
                    except Exception:
                        pass

        # Decision -> Activity = REQUIRES
        for decision in decisions:
            for activity in activities:
                dec_node = entity_to_node.get(decision.id)
                act_node = entity_to_node.get(activity.id)
                if dec_node and act_node:
                    try:
                        await self._graph.create_relationship(
                            from_id=dec_node,
                            to_id=act_node,
                            relationship_type="REQUIRES",
                            properties={"inferred": True},
                        )
                        count += 1
                    except Exception:
                        pass

        return count

    async def _generate_and_store_embeddings(
        self,
        session: AsyncSession,
        fragments: list[tuple[str, str, str]],
    ) -> tuple[int, list[str]]:
        """Generate and store embeddings for fragments.

        Args:
            session: Database session.
            fragments: List of (fragment_id, content, evidence_id) tuples.

        Returns:
            Tuple of (count of embeddings stored, list of error messages).
        """
        count = 0
        errors: list[str] = []
        for fragment_id, content, _ in fragments:
            try:
                embedding = self._embeddings.generate_embedding(content)
                await self._embeddings.store_embedding(session, fragment_id, embedding)
                count += 1
            except Exception as e:
                msg = f"Embedding failed for fragment {fragment_id}: {e}"
                errors.append(msg)
                logger.warning("Failed to generate embedding for fragment %s: %s", fragment_id, e)

        return count, errors

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
        resolved_entities = resolve_entities(all_entities)
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
