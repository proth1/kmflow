"""Entity extraction wrapper for the consensus algorithm.

Step 2: Uses the semantic/entity_extraction module to extract activities,
decisions, roles, systems, and documents from evidence fragments. Builds
a mapping from entities to their source evidence items.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.core.models import EvidenceFragment, EvidenceItem
from src.semantic.entity_extraction import (
    DuplicateCandidate,
    ExtractedEntity,
    ExtractionResult,
    extract_entities,
    resolve_entities,
)

logger = logging.getLogger(__name__)


@dataclass
class ExtractionSummary:
    """Summary of entity extraction across all evidence.

    Attributes:
        entities: List of resolved (deduplicated) entities.
        raw_entity_count: Total entities before resolution.
        entity_to_evidence: Maps entity ID to list of evidence item IDs.
        entity_to_fragments: Maps entity ID to list of fragment IDs.
        duplicate_candidates: Pairs of entities flagged as potential duplicates.
    """

    entities: list[ExtractedEntity] = field(default_factory=list)
    raw_entity_count: int = 0
    entity_to_evidence: dict[str, list[str]] = field(default_factory=dict)
    entity_to_fragments: dict[str, list[str]] = field(default_factory=dict)
    duplicate_candidates: list[DuplicateCandidate] = field(default_factory=list)


async def extract_from_evidence(
    evidence_items: list[EvidenceItem],
    fragments: list[EvidenceFragment],
    seed_terms: list[str] | None = None,
) -> ExtractionSummary:
    """Extract and resolve entities from evidence fragments.

    Runs entity extraction on each fragment, tracks which evidence
    items each entity came from, then resolves (deduplicates) entities.

    If seed_terms are provided, entities matching seed terms receive a
    confidence boost during extraction.

    Args:
        evidence_items: List of evidence items (for metadata).
        fragments: List of fragments to extract entities from.
        seed_terms: Canonical terms from the engagement seed list.

    Returns:
        ExtractionSummary with resolved entities, provenance maps, and
        duplicate candidate pairs.
    """
    # Build fragment -> evidence item mapping
    fragment_to_evidence: dict[str, str] = {}
    for item in evidence_items:
        for fragment in item.fragments:
            fragment_to_evidence[str(fragment.id)] = str(item.id)

    all_entities: list[ExtractedEntity] = []
    entity_to_evidence: dict[str, list[str]] = {}
    entity_to_fragments: dict[str, list[str]] = {}

    for fragment in fragments:
        frag_id = str(fragment.id)
        evidence_id = fragment_to_evidence.get(frag_id, str(fragment.evidence_id))

        result: ExtractionResult = await extract_entities(fragment.content, fragment_id=frag_id, seed_terms=seed_terms)

        for entity in result.entities:
            all_entities.append(entity)

            # Track evidence provenance
            if entity.id not in entity_to_evidence:
                entity_to_evidence[entity.id] = []
            if evidence_id not in entity_to_evidence[entity.id]:
                entity_to_evidence[entity.id].append(evidence_id)

            # Track fragment provenance
            if entity.id not in entity_to_fragments:
                entity_to_fragments[entity.id] = []
            if frag_id not in entity_to_fragments[entity.id]:
                entity_to_fragments[entity.id].append(frag_id)

    raw_count = len(all_entities)

    # Resolve entities (merge near-duplicates) and detect duplicate candidates
    resolved, duplicate_candidates = resolve_entities(all_entities)

    # After resolution, merge provenance maps for merged entities
    # The resolved entities keep the canonical ID, so the maps still work
    # but we need to handle alias merging
    merged_to_evidence: dict[str, list[str]] = {}
    merged_to_fragments: dict[str, list[str]] = {}

    for entity in resolved:
        ev_ids: list[str] = list(entity_to_evidence.get(entity.id, []))
        frag_ids: list[str] = list(entity_to_fragments.get(entity.id, []))
        merged_to_evidence[entity.id] = ev_ids
        merged_to_fragments[entity.id] = frag_ids

    logger.info(
        "Extracted %d raw entities, resolved to %d unique entities",
        raw_count,
        len(resolved),
    )

    return ExtractionSummary(
        entities=resolved,
        raw_entity_count=raw_count,
        entity_to_evidence=merged_to_evidence,
        entity_to_fragments=merged_to_fragments,
        duplicate_candidates=duplicate_candidates,
    )
