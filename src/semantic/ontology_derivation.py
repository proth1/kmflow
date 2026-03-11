"""Ontology derivation engine (KMFLOW-6).

Derives a formal domain ontology from an engagement's seed terms and
Neo4j knowledge graph relationships. Pipeline:

1. Query Neo4j for relationship patterns between entity types
2. Cluster seed terms by category into ontology classes
3. Map typed edges to ontology properties with domain/range
4. Generate axioms from validated high-frequency patterns
5. Compute completeness score
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter, defaultdict
from typing import Any

from neo4j import AsyncDriver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.ontology import (
    OntologyAxiom,
    OntologyClass,
    OntologyProperty,
    OntologyStatus,
    OntologyVersion,
)
from src.core.models.seed_term import SeedTerm, TermStatus
from src.semantic.ontology.loader import get_valid_relationship_types

logger = logging.getLogger(__name__)

# Minimum relationship frequency to generate an axiom
AXIOM_FREQUENCY_THRESHOLD = 3
# Minimum confidence for axiom generation
AXIOM_CONFIDENCE_THRESHOLD = 0.6


class OntologyDerivationService:
    """Derives domain ontologies from seed terms and knowledge graph patterns."""

    def __init__(self, session: AsyncSession, neo4j_driver: AsyncDriver) -> None:
        self.session = session
        self.neo4j_driver = neo4j_driver

    async def derive(self, engagement_id: uuid.UUID) -> dict[str, Any]:
        """Run the full ontology derivation pipeline for an engagement.

        Returns a summary dict with ontology ID, class/property/axiom counts,
        and completeness score.
        """
        # Determine next version number
        result = await self.session.execute(
            select(OntologyVersion)
            .where(OntologyVersion.engagement_id == engagement_id)
            .order_by(OntologyVersion.version.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        next_version = (latest.version + 1) if latest else 1

        # Create ontology version
        ontology = OntologyVersion(
            engagement_id=engagement_id,
            version=next_version,
            status=OntologyStatus.DERIVING,
        )
        self.session.add(ontology)
        await self.session.flush()

        # Step 1: Get seed terms
        seed_terms = await self._get_seed_terms(engagement_id)

        # Step 2: Create classes from seed term categories
        classes = await self._create_classes(ontology.id, seed_terms)

        # Step 3: Extract relationship patterns from Neo4j
        patterns = await self._extract_relationship_patterns(engagement_id)

        # Step 4: Create properties from relationship patterns
        properties = await self._create_properties(ontology.id, patterns, classes)

        # Step 5: Generate axioms from frequent patterns
        axioms = await self._generate_axioms(ontology.id, patterns, classes)

        # Step 6: Compute completeness
        completeness = self._compute_completeness(seed_terms, classes, properties)

        # Update ontology version
        ontology.status = OntologyStatus.DERIVED
        ontology.class_count = len(classes)
        ontology.property_count = len(properties)
        ontology.axiom_count = len(axioms)
        ontology.completeness_score = completeness

        await self.session.commit()

        return {
            "ontology_id": str(ontology.id),
            "version": ontology.version,
            "status": ontology.status.value,
            "class_count": len(classes),
            "property_count": len(properties),
            "axiom_count": len(axioms),
            "completeness_score": completeness,
        }

    async def _get_seed_terms(self, engagement_id: uuid.UUID) -> list[SeedTerm]:
        """Fetch active seed terms for the engagement."""
        result = await self.session.execute(
            select(SeedTerm).where(
                SeedTerm.engagement_id == engagement_id,
                SeedTerm.status == TermStatus.ACTIVE,
            )
        )
        return list(result.scalars().all())

    async def _create_classes(self, ontology_id: uuid.UUID, seed_terms: list[SeedTerm]) -> dict[str, OntologyClass]:
        """Create ontology classes from seed term categories.

        Groups seed terms by category and creates a class for each category.
        Individual terms become instances recorded in source_seed_terms.
        """
        by_category: dict[str, list[SeedTerm]] = defaultdict(list)
        for term in seed_terms:
            by_category[term.category.value].append(term)

        classes: dict[str, OntologyClass] = {}
        for category, terms in by_category.items():
            cls = OntologyClass(
                ontology_id=ontology_id,
                name=category.replace("_", " ").title(),
                description=f"Domain class derived from {len(terms)} seed terms in the '{category}' category",
                source_seed_terms={
                    "terms": [{"term": t.term, "domain": t.domain} for t in terms],
                    "count": len(terms),
                },
                instance_count=len(terms),
                confidence=min(1.0, len(terms) / 10.0),
            )
            self.session.add(cls)
            await self.session.flush()
            classes[category] = cls

        return classes

    async def _extract_relationship_patterns(self, engagement_id: uuid.UUID) -> list[dict[str, Any]]:
        """Query Neo4j for relationship patterns in this engagement's graph.

        Returns a list of pattern dicts with source_label, target_label,
        relationship_type, and count.
        """
        query = """
        MATCH (a)-[r]->(b)
        WHERE a.engagement_id = $engagement_id AND b.engagement_id = $engagement_id
        RETURN labels(a)[0] AS source_label, type(r) AS rel_type,
               labels(b)[0] AS target_label, count(*) AS cnt
        ORDER BY cnt DESC
        """
        patterns: list[dict[str, Any]] = []
        try:
            async with self.neo4j_driver.session() as neo_session:
                result = await neo_session.run(query, engagement_id=str(engagement_id))
                records = await result.data()
                for record in records:
                    patterns.append(
                        {
                            "source_label": record["source_label"],
                            "relationship_type": record["rel_type"],
                            "target_label": record["target_label"],
                            "count": record["cnt"],
                        }
                    )
        except Exception:
            logger.warning("Neo4j pattern extraction failed; continuing with empty patterns")

        return patterns

    async def _create_properties(
        self,
        ontology_id: uuid.UUID,
        patterns: list[dict[str, Any]],
        classes: dict[str, OntologyClass],
    ) -> list[OntologyProperty]:
        """Create ontology properties from relationship patterns.

        Maps each unique relationship type to a property with domain/range
        inferred from the most frequent source/target labels.
        """
        valid_rel_types = get_valid_relationship_types()

        # Group patterns by relationship type
        by_rel: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for p in patterns:
            by_rel[p["relationship_type"]].append(p)

        properties: list[OntologyProperty] = []
        for rel_type, rel_patterns in by_rel.items():
            if rel_type not in valid_rel_types:
                continue

            total_count = sum(p["count"] for p in rel_patterns)

            # Find most common domain/range labels
            source_counts: Counter[str] = Counter()
            target_counts: Counter[str] = Counter()
            for p in rel_patterns:
                source_counts[p["source_label"]] += p["count"]
                target_counts[p["target_label"]] += p["count"]

            top_source = source_counts.most_common(1)[0][0] if source_counts else None
            top_target = target_counts.most_common(1)[0][0] if target_counts else None

            # Map Neo4j labels to ontology classes (lowercase match)
            domain_class = classes.get(top_source.lower()) if top_source else None
            range_class = classes.get(top_target.lower()) if top_target else None

            prop = OntologyProperty(
                ontology_id=ontology_id,
                name=rel_type.lower().replace("_", " "),
                source_edge_type=rel_type,
                domain_class_id=domain_class.id if domain_class else None,
                range_class_id=range_class.id if range_class else None,
                usage_count=total_count,
                confidence=min(1.0, total_count / 20.0),
            )
            self.session.add(prop)
            properties.append(prop)

        await self.session.flush()
        return properties

    async def _generate_axioms(
        self,
        ontology_id: uuid.UUID,
        patterns: list[dict[str, Any]],
        classes: dict[str, OntologyClass],
    ) -> list[OntologyAxiom]:
        """Generate axioms from frequent, high-confidence patterns.

        Axiom types:
        - existential: "Every X has at least one Y via R" (when frequency >= threshold)
        - domain_range: "R always connects X to Y" (when pattern is exclusive)
        """
        axioms: list[OntologyAxiom] = []

        # Group by (source_label, rel_type)
        by_source_rel: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for p in patterns:
            by_source_rel[(p["source_label"], p["relationship_type"])].append(p)

        for (source_label, rel_type), rel_patterns in by_source_rel.items():
            total = sum(p["count"] for p in rel_patterns)
            if total < AXIOM_FREQUENCY_THRESHOLD:
                continue

            confidence = min(1.0, total / 20.0)
            if confidence < AXIOM_CONFIDENCE_THRESHOLD:
                continue

            # Check if there's a dominant target
            target_counts: Counter[str] = Counter()
            for p in rel_patterns:
                target_counts[p["target_label"]] += p["count"]

            top_target, top_count = target_counts.most_common(1)[0]
            exclusivity = top_count / total if total > 0 else 0

            # Existential axiom
            axiom = OntologyAxiom(
                ontology_id=ontology_id,
                expression=f"Every {source_label} {rel_type.lower().replace('_', ' ')} at least one {top_target}",
                axiom_type="existential",
                source_pattern={
                    "source_label": source_label,
                    "relationship_type": rel_type,
                    "target_label": top_target,
                    "frequency": total,
                    "exclusivity": round(exclusivity, 2),
                },
                confidence=confidence,
            )
            self.session.add(axiom)
            axioms.append(axiom)

            # Domain/range axiom if pattern is highly exclusive (>80%)
            if exclusivity > 0.8:
                dr_axiom = OntologyAxiom(
                    ontology_id=ontology_id,
                    expression=f"{rel_type} domain is {source_label} and range is {top_target}",
                    axiom_type="domain_range",
                    source_pattern={
                        "source_label": source_label,
                        "relationship_type": rel_type,
                        "target_label": top_target,
                        "exclusivity": round(exclusivity, 2),
                    },
                    confidence=confidence * exclusivity,
                )
                self.session.add(dr_axiom)
                axioms.append(dr_axiom)

        await self.session.flush()
        return axioms

    def _compute_completeness(
        self,
        seed_terms: list[SeedTerm],
        classes: dict[str, OntologyClass],
        properties: list[OntologyProperty],
    ) -> float:
        """Compute ontology completeness score (0.0 - 1.0).

        Factors:
        - Category coverage: what fraction of seed term categories have classes (40%)
        - Term coverage: what fraction of seed terms are represented (30%)
        - Property coverage: classes with at least one property (30%)
        """
        if not seed_terms:
            return 0.0

        # Category coverage
        all_categories = {t.category.value for t in seed_terms}
        covered_categories = set(classes.keys())
        category_score = len(covered_categories & all_categories) / len(all_categories) if all_categories else 0

        # Term coverage (all terms mapped to classes)
        term_score = 1.0 if classes else 0.0

        # Property coverage (classes with at least one domain/range reference)
        if classes:
            class_ids = {c.id for c in classes.values()}
            connected_ids = set()
            for p in properties:
                if p.domain_class_id in class_ids:
                    connected_ids.add(p.domain_class_id)
                if p.range_class_id in class_ids:
                    connected_ids.add(p.range_class_id)
            property_score = len(connected_ids) / len(class_ids)
        else:
            property_score = 0.0

        return round(0.4 * category_score + 0.3 * term_score + 0.3 * property_score, 2)


class OntologyValidationService:
    """Validates a derived ontology for completeness and quality."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def validate(self, ontology_id: uuid.UUID) -> dict[str, Any]:
        """Run completeness validation on a derived ontology.

        Returns a validation report with orphan classes, disconnected subgraphs,
        completeness score, and enrichment recommendations.
        """
        ontology = await self.session.get(OntologyVersion, ontology_id)
        if not ontology:
            return {"error": "Ontology not found"}

        # Get all classes
        result = await self.session.execute(select(OntologyClass).where(OntologyClass.ontology_id == ontology_id))
        classes = list(result.scalars().all())

        # Get all properties
        result = await self.session.execute(select(OntologyProperty).where(OntologyProperty.ontology_id == ontology_id))
        properties = list(result.scalars().all())

        # Get all axioms
        result = await self.session.execute(select(OntologyAxiom).where(OntologyAxiom.ontology_id == ontology_id))
        axioms = list(result.scalars().all())

        # Find orphan classes (no incoming or outgoing properties)
        connected_ids: set[uuid.UUID] = set()
        for p in properties:
            if p.domain_class_id:
                connected_ids.add(p.domain_class_id)
            if p.range_class_id:
                connected_ids.add(p.range_class_id)

        orphans = [c for c in classes if c.id not in connected_ids]

        # Build adjacency for disconnected subgraph detection
        adjacency: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        for p in properties:
            if p.domain_class_id and p.range_class_id:
                adjacency[p.domain_class_id].add(p.range_class_id)
                adjacency[p.range_class_id].add(p.domain_class_id)

        # BFS to find connected components
        visited: set[uuid.UUID] = set()
        components: list[list[str]] = []
        class_map = {c.id: c.name for c in classes}

        for cls in classes:
            if cls.id in visited or cls.id not in adjacency:
                continue
            component: list[str] = []
            queue = [cls.id]
            while queue:
                node = queue.pop()
                if node in visited:
                    continue
                visited.add(node)
                component.append(class_map.get(node, str(node)))
                for neighbor in adjacency[node]:
                    if neighbor not in visited:
                        queue.append(neighbor)
            components.append(component)

        # Generate recommendations
        recommendations: list[str] = []
        if orphans:
            for o in orphans:
                recommendations.append(
                    f"Class '{o.name}' has no relationships — add seed terms or evidence to connect it"
                )
        if len(components) > 1:
            recommendations.append(
                f"Ontology has {len(components)} disconnected subgraphs — consider adding bridging relationships"
            )
        if not axioms:
            recommendations.append("No axioms generated — more evidence and relationship patterns needed")

        # Low-confidence classes
        low_conf = [c for c in classes if c.confidence < 0.5]
        if low_conf:
            recommendations.append(f"{len(low_conf)} classes have low confidence (<0.5) — add more seed terms")

        # Update ontology status
        ontology.status = OntologyStatus.VALIDATED
        await self.session.commit()

        return {
            "ontology_id": str(ontology_id),
            "completeness_score": ontology.completeness_score,
            "class_count": len(classes),
            "property_count": len(properties),
            "axiom_count": len(axioms),
            "orphan_classes": [{"name": o.name, "instance_count": o.instance_count} for o in orphans],
            "disconnected_subgraphs": components if len(components) > 1 else [],
            "recommendations": recommendations,
        }
