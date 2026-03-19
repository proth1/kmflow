"""Entity extraction quality evaluation.

Compares extracted entities (from EvidenceFragment.metadata_json) against
EntityAnnotation ground truth to compute standard P/R/F1 metrics, broken
down by entity type and evidence parser category.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import uuid
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.evidence import EvidenceFragment, EvidenceItem
from src.core.models.pipeline_quality import EntityAnnotation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fuzzy name matching
# ---------------------------------------------------------------------------


def _fuzzy_match(name1: str, name2: str, threshold: float = 0.85) -> bool:
    """Return True if name1 and name2 are sufficiently similar.

    Uses difflib.SequenceMatcher (Levenshtein-like ratio) normalised to [0, 1].
    Case-insensitive comparison.

    Args:
        name1: First entity name string.
        name2: Second entity name string.
        threshold: Minimum similarity ratio to count as a match (default 0.85).

    Returns:
        True if the similarity ratio is >= threshold.
    """
    ratio = SequenceMatcher(None, name1.lower(), name2.lower()).ratio()
    return ratio >= threshold


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _content_hash(content: str) -> str:
    """SHA-256 hex digest of the fragment content (matches EntityAnnotation.fragment_content_hash)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _extracted_entities_from_fragment(fragment: EvidenceFragment) -> list[dict[str, Any]]:
    """Parse entities from a fragment's metadata_json field.

    Expected structure (stored as JSON text or dict)::

        {"entities": [{"type": "PERSON", "name": "Alice"}, ...]}

    Returns:
        List of dicts with at minimum "type" and "name" keys. Returns [] on
        parse failure or missing keys.
    """
    raw = fragment.metadata_json
    if not raw:
        return []
    try:
        data: dict[str, Any] = json.loads(raw) if isinstance(raw, str) else raw
        return data.get("entities", [])
    except (json.JSONDecodeError, AttributeError):
        logger.debug("Could not parse metadata_json for fragment %s", fragment.id)
        return []


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    """Compute precision, recall, and F1 from confusion matrix counts."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def evaluate_extraction(session: AsyncSession, evidence_item_id: uuid.UUID) -> dict[str, Any]:
    """Compare extracted entities against annotated ground truth for one evidence item.

    For each fragment belonging to the item, the extracted entities in
    ``metadata_json`` are matched (fuzzy, case-insensitive) against
    EntityAnnotation rows with the same content hash.

    Args:
        session: Async database session.
        evidence_item_id: UUID of the EvidenceItem to evaluate.

    Returns:
        Dict with keys: precision, recall, f1, true_positives,
        false_positives, false_negatives, evidence_item_id.
    """
    # Load fragments for this evidence item
    frag_stmt = select(EvidenceFragment).where(EvidenceFragment.evidence_id == evidence_item_id)
    frag_result = await session.execute(frag_stmt)
    fragments = list(frag_result.scalars().all())

    # Load ground-truth annotations for this evidence item
    ann_stmt = select(EntityAnnotation).where(EntityAnnotation.evidence_item_id == evidence_item_id)
    ann_result = await session.execute(ann_stmt)
    annotations = list(ann_result.scalars().all())

    # Index annotations by content hash
    ann_by_hash: dict[str, list[EntityAnnotation]] = defaultdict(list)
    for ann in annotations:
        ann_by_hash[ann.fragment_content_hash].append(ann)

    tp = fp = fn = 0

    for fragment in fragments:
        fhash = _content_hash(fragment.content)
        ground_truth = ann_by_hash.get(fhash, [])
        extracted = _extracted_entities_from_fragment(fragment)

        matched_gt: set[int] = set()

        for ext in extracted:
            ext_type = ext.get("type", "")
            ext_name = ext.get("name", "")
            found = False
            for gt_idx, gt in enumerate(ground_truth):
                if gt_idx in matched_gt:
                    continue
                if gt.entity_type == ext_type and _fuzzy_match(gt.entity_name, ext_name):
                    tp += 1
                    matched_gt.add(gt_idx)
                    found = True
                    break
            if not found:
                fp += 1

        # Ground truth entities not matched are false negatives
        fn += len(ground_truth) - len(matched_gt)

    metrics = _prf(tp, fp, fn)
    metrics.update(
        {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "evidence_item_id": str(evidence_item_id),  # type: ignore[dict-item]
        }
    )
    return metrics


async def evaluate_by_entity_type(session: AsyncSession, engagement_id: uuid.UUID) -> list[dict[str, Any]]:
    """Per-entity-type precision/recall/F1 breakdown for an engagement.

    Iterates all evidence items in the engagement and aggregates confusion
    matrix counts by entity type across all fragments.

    Args:
        session: Async database session.
        engagement_id: UUID of the engagement to evaluate.

    Returns:
        List of dicts, one per entity type, with keys: entity_type,
        precision, recall, f1, true_positives, false_positives, false_negatives.
        Sorted by entity_type ascending.
    """
    item_stmt = select(EvidenceItem).where(EvidenceItem.engagement_id == engagement_id)
    item_result = await session.execute(item_stmt)
    evidence_items = list(item_result.scalars().all())

    # Aggregate counts by entity type: {type -> {tp, fp, fn}}
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

    for item in evidence_items:
        frag_stmt = select(EvidenceFragment).where(EvidenceFragment.evidence_id == item.id)
        frag_result = await session.execute(frag_stmt)
        fragments = list(frag_result.scalars().all())

        ann_stmt = select(EntityAnnotation).where(EntityAnnotation.evidence_item_id == item.id)
        ann_result = await session.execute(ann_stmt)
        annotations = list(ann_result.scalars().all())

        ann_by_hash: dict[str, list[EntityAnnotation]] = defaultdict(list)
        for ann in annotations:
            ann_by_hash[ann.fragment_content_hash].append(ann)

        for fragment in fragments:
            fhash = _content_hash(fragment.content)
            ground_truth = ann_by_hash.get(fhash, [])
            extracted = _extracted_entities_from_fragment(fragment)

            matched_gt: set[int] = set()

            for ext in extracted:
                ext_type = ext.get("type", "")
                ext_name = ext.get("name", "")
                found = False
                for gt_idx, gt in enumerate(ground_truth):
                    if gt_idx in matched_gt:
                        continue
                    if gt.entity_type == ext_type and _fuzzy_match(gt.entity_name, ext_name):
                        counts[ext_type]["tp"] += 1
                        matched_gt.add(gt_idx)
                        found = True
                        break
                if not found:
                    counts[ext_type]["fp"] += 1

            for gt_idx, gt in enumerate(ground_truth):
                if gt_idx not in matched_gt:
                    counts[gt.entity_type]["fn"] += 1

    rows: list[dict[str, Any]] = []
    for entity_type, c in sorted(counts.items()):
        metrics = _prf(c["tp"], c["fp"], c["fn"])
        metrics.update(
            {
                "entity_type": entity_type,  # type: ignore[dict-item]
                "true_positives": c["tp"],
                "false_positives": c["fp"],
                "false_negatives": c["fn"],
            }
        )
        rows.append(metrics)
    return rows


async def evaluate_by_parser(session: AsyncSession, engagement_id: uuid.UUID) -> list[dict[str, Any]]:
    """Per-evidence-category (parser) precision/recall/F1 breakdown for an engagement.

    Groups evidence items by their category (which maps to the parser used),
    then aggregates extraction metrics per category.

    Args:
        session: Async database session.
        engagement_id: UUID of the engagement to evaluate.

    Returns:
        List of dicts, one per evidence category, with keys: category,
        precision, recall, f1, true_positives, false_positives, false_negatives,
        evidence_item_count. Sorted by category ascending.
    """
    item_stmt = select(EvidenceItem).where(EvidenceItem.engagement_id == engagement_id)
    item_result = await session.execute(item_stmt)
    evidence_items = list(item_result.scalars().all())

    # Aggregate counts by category
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "item_count": 0})

    for item in evidence_items:
        category = str(item.category)
        counts[category]["item_count"] += 1

        frag_stmt = select(EvidenceFragment).where(EvidenceFragment.evidence_id == item.id)
        frag_result = await session.execute(frag_stmt)
        fragments = list(frag_result.scalars().all())

        ann_stmt = select(EntityAnnotation).where(EntityAnnotation.evidence_item_id == item.id)
        ann_result = await session.execute(ann_stmt)
        annotations = list(ann_result.scalars().all())

        ann_by_hash: dict[str, list[EntityAnnotation]] = defaultdict(list)
        for ann in annotations:
            ann_by_hash[ann.fragment_content_hash].append(ann)

        for fragment in fragments:
            fhash = _content_hash(fragment.content)
            ground_truth = ann_by_hash.get(fhash, [])
            extracted = _extracted_entities_from_fragment(fragment)

            matched_gt: set[int] = set()

            for ext in extracted:
                ext_type = ext.get("type", "")
                ext_name = ext.get("name", "")
                found = False
                for gt_idx, gt in enumerate(ground_truth):
                    if gt_idx in matched_gt:
                        continue
                    if gt.entity_type == ext_type and _fuzzy_match(gt.entity_name, ext_name):
                        counts[category]["tp"] += 1
                        matched_gt.add(gt_idx)
                        found = True
                        break
                if not found:
                    counts[category]["fp"] += 1

            for gt_idx, _gt in enumerate(ground_truth):
                if gt_idx not in matched_gt:
                    counts[category]["fn"] += 1

    rows: list[dict[str, Any]] = []
    for category, c in sorted(counts.items()):
        metrics = _prf(c["tp"], c["fp"], c["fn"])
        metrics.update(
            {
                "category": category,  # type: ignore[dict-item]
                "true_positives": c["tp"],
                "false_positives": c["fp"],
                "false_negatives": c["fn"],
                "evidence_item_count": c["item_count"],
            }
        )
        rows.append(metrics)
    return rows


async def get_coverage_metrics(session: AsyncSession, engagement_id: uuid.UUID) -> dict[str, Any]:
    """Compute entity coverage statistics for an engagement.

    Returns distribution information useful for diagnosing pipeline gaps:
    entity density, type distribution, zero-entity fragments, and confidence
    distribution by entity type.

    Args:
        session: Async database session.
        engagement_id: UUID of the engagement to analyse.

    Returns:
        Dict with keys:
          - total_fragments: int
          - fragments_with_entities: int
          - fragments_without_entities: int
          - avg_entities_per_fragment: float
          - entities_per_fragment_distribution: dict[str, int] (bucket -> count)
          - entity_type_distribution: dict[str, int] (entity_type -> count)
          - confidence_by_type: dict[str, dict] (entity_type -> {min, max, mean})
    """
    item_stmt = select(EvidenceItem).where(EvidenceItem.engagement_id == engagement_id)
    item_result = await session.execute(item_stmt)
    evidence_items = list(item_result.scalars().all())

    total_fragments = 0
    fragments_with_entities = 0
    entity_counts_per_fragment: list[int] = []
    type_distribution: dict[str, int] = defaultdict(int)
    confidence_by_type: dict[str, list[float]] = defaultdict(list)

    for item in evidence_items:
        frag_stmt = select(EvidenceFragment).where(EvidenceFragment.evidence_id == item.id)
        frag_result = await session.execute(frag_stmt)
        fragments = list(frag_result.scalars().all())

        for fragment in fragments:
            total_fragments += 1
            extracted = _extracted_entities_from_fragment(fragment)
            count = len(extracted)
            entity_counts_per_fragment.append(count)
            if count > 0:
                fragments_with_entities += 1
            for ext in extracted:
                etype = ext.get("type", "UNKNOWN")
                type_distribution[etype] += 1
                conf = ext.get("confidence")
                if conf is not None:
                    with contextlib.suppress(TypeError, ValueError):
                        confidence_by_type[etype].append(float(conf))

    # Build bucket distribution for entities per fragment
    bucket_distribution: dict[str, int] = {"0": 0, "1-5": 0, "6-10": 0, "11-20": 0, "21+": 0}
    for c in entity_counts_per_fragment:
        if c == 0:
            bucket_distribution["0"] += 1
        elif c <= 5:
            bucket_distribution["1-5"] += 1
        elif c <= 10:
            bucket_distribution["6-10"] += 1
        elif c <= 20:
            bucket_distribution["11-20"] += 1
        else:
            bucket_distribution["21+"] += 1

    avg_entities = sum(entity_counts_per_fragment) / total_fragments if total_fragments > 0 else 0.0

    # Confidence stats per type
    conf_stats: dict[str, dict[str, float]] = {}
    for etype, values in confidence_by_type.items():
        if values:
            conf_stats[etype] = {
                "min": min(values),
                "max": max(values),
                "mean": sum(values) / len(values),
                "count": len(values),
            }

    return {
        "total_fragments": total_fragments,
        "fragments_with_entities": fragments_with_entities,
        "fragments_without_entities": total_fragments - fragments_with_entities,
        "avg_entities_per_fragment": avg_entities,
        "entities_per_fragment_distribution": dict(bucket_distribution),
        "entity_type_distribution": dict(type_distribution),
        "confidence_by_type": conf_stats,
    }
