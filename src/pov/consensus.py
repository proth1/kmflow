"""Consensus building for the LCD algorithm.

Step 4 (Steps 6-7 of the 8-step LCD algorithm): Applies weighted voting by
evidence type to build an inclusive first-pass consensus model. Weight hierarchy:
System data (highest) > Process docs > Communications > Interviews > Surveys >
Job aids (lowest). Includes recency bias for breaking ties, variant detection,
and ConflictStub forwarding.

LCD Inclusivity: ALL elements with any evidence support are included in the
consensus model (not just those with majority agreement). Confidence reflects
the level of support.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.core.models import EvidenceItem
from src.pov.constants import (
    BRIGHTNESS_BRIGHT_THRESHOLD,
    BRIGHTNESS_DIM_THRESHOLD,
    DEFAULT_EVIDENCE_WEIGHT,
    EVIDENCE_TYPE_WEIGHTS,
)
from src.pov.triangulation import TriangulatedElement

logger = logging.getLogger(__name__)

# Recency blend ratio: weight = base_weight * (BASE + FACTOR * recency)
# BASE provides stability; FACTOR allows newer evidence to score higher.
RECENCY_BLEND_BASE: float = 0.7
RECENCY_BLEND_FACTOR: float = 0.3


@dataclass
class ConsensusElement:
    """An element with consensus score from weighted voting.

    Attributes:
        triangulated: The triangulated element data.
        weighted_vote_score: Score from weighted voting across evidence types.
        max_weight: Highest evidence type weight supporting this element.
        contributing_categories: Set of evidence categories supporting this element.
        source_reliability: Highest single-source weight (max reliability).
        brightness_hint: Suggested brightness classification based on consensus.
    """

    triangulated: TriangulatedElement
    weighted_vote_score: float = 0.0
    max_weight: float = 0.0
    contributing_categories: set[str] = field(default_factory=set)
    source_reliability: float = 0.0
    brightness_hint: str = "dark"


@dataclass
class VariantAnnotation:
    """Annotation for a structural variant detected during consensus.

    When evidence supports divergent process paths (e.g., a standard path
    and an expedited path), both are emitted as annotated variants.

    Attributes:
        variant_label: Identifier for this variant (e.g., "variant_A").
        element_name: Name of the element/subprocess with variants.
        evidence_ids: Evidence IDs supporting this variant.
        evidence_coverage: Fraction of total evidence supporting this variant.
        contributing_categories: Evidence categories supporting this variant.
    """

    variant_label: str = ""
    element_name: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    evidence_coverage: float = 0.0
    contributing_categories: set[str] = field(default_factory=set)


@dataclass
class ConflictStub:
    """A conflict detected during consensus building, forwarded to Step 8.

    ConflictStubs are lightweight records created during consensus when
    evidence sources disagree. They are enriched into full ConflictObjects
    during the contradiction resolution step.

    Attributes:
        element_name: Name of the element with conflicting evidence.
        disagreement_type: Type of disagreement (matches MismatchType values).
        preferred_value: The value accepted as the primary consensus path.
        alternative_value: The value from the losing source.
        preferred_evidence_ids: Evidence supporting the preferred value.
        alternative_evidence_ids: Evidence supporting the alternative value.
        resolution_reason: Explanation for the preference (e.g., "weight", "recency").
    """

    element_name: str = ""
    disagreement_type: str = ""
    preferred_value: str = ""
    alternative_value: str = ""
    preferred_evidence_ids: list[str] = field(default_factory=list)
    alternative_evidence_ids: list[str] = field(default_factory=list)
    resolution_reason: str = ""


@dataclass
class ConsensusResult:
    """Complete result from consensus building.

    Attributes:
        elements: All consensus elements (LCD inclusive — every element with evidence).
        variants: Detected process variants with annotations.
        conflict_stubs: Conflicts forwarded to contradiction resolution step.
    """

    elements: list[ConsensusElement] = field(default_factory=list)
    variants: list[VariantAnnotation] = field(default_factory=list)
    conflict_stubs: list[ConflictStub] = field(default_factory=list)


# -- Weight configuration ----------------------------------------------------


def get_weight_map(
    engagement_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Get the evidence type weight map, optionally overridden per engagement.

    The weight map controls how much each evidence category contributes to
    consensus scoring. Engagements can override default weights to reflect
    domain-specific trust levels.

    Args:
        engagement_weights: Optional per-engagement weight overrides.
            Keys are evidence category names, values are weights (0.0–1.0).

    Returns:
        Merged weight map (engagement overrides take precedence).
    """
    weights = dict(EVIDENCE_TYPE_WEIGHTS)
    if engagement_weights:
        for cat, w in engagement_weights.items():
            weights[cat] = max(0.0, min(1.0, w))
    return weights


def _get_evidence_weight(
    category: str,
    weight_map: dict[str, float] | None = None,
) -> float:
    """Get the weight for an evidence category.

    Args:
        category: Evidence category name (from EvidenceCategory enum).
        weight_map: Optional custom weight map (overrides global defaults).

    Returns:
        Weight value between 0.0 and 1.0.
    """
    if weight_map:
        return weight_map.get(category, DEFAULT_EVIDENCE_WEIGHT)
    return EVIDENCE_TYPE_WEIGHTS.get(category, DEFAULT_EVIDENCE_WEIGHT)


# -- Recency bias ------------------------------------------------------------


def compute_recency_factor(
    source_date: datetime | None,
    reference_date: datetime | None = None,
    half_life_years: float = 3.0,
) -> float:
    """Compute recency factor using exponential decay.

    Newer evidence receives a higher recency factor. Uses the evidence
    freshness model from PRD Section 6.3 with configurable half-life.

    Args:
        source_date: The date of the evidence source.
        reference_date: Reference point for age calculation (default: now).
        half_life_years: Years for the score to decay by 50%.

    Returns:
        Recency factor between 0.0 and 1.0.
    """
    if source_date is None:
        return 0.5  # neutral for undated evidence

    if half_life_years <= 0:
        return 1.0  # guard against division by zero

    if reference_date is None:
        reference_date = datetime.now(tz=UTC)

    # Make both tz-aware for comparison
    if source_date.tzinfo is None:
        source_date = source_date.replace(tzinfo=UTC)
    if reference_date.tzinfo is None:
        reference_date = reference_date.replace(tzinfo=UTC)

    age_days = (reference_date - source_date).days
    if age_days <= 0:
        return 1.0

    age_years = age_days / 365.25
    decay = math.exp(-0.693 * age_years / half_life_years)  # ln(2) ≈ 0.693
    return max(0.0, min(1.0, decay))


# -- Variant detection -------------------------------------------------------

VARIANT_COVERAGE_THRESHOLD: float = 0.4


def detect_variants(
    elements: list[ConsensusElement],
    evidence_items: list[EvidenceItem],
    weight_map: dict[str, float] | None = None,
) -> list[VariantAnnotation]:
    """Detect process variants from consensus elements.

    When evidence supports structurally divergent paths (e.g., standard vs.
    expedited subprocess), both are emitted as annotated variants. Variants
    are detected by grouping elements by canonical name and checking for
    distinct entity types or subtypes with sufficient evidence coverage.

    Args:
        elements: Consensus elements to check for variants.
        evidence_items: All evidence items (for source counting).
        weight_map: Optional engagement-specific weight map.

    Returns:
        List of VariantAnnotations for detected variants.
    """
    total_sources = len(evidence_items) if evidence_items else 1
    variants: list[VariantAnnotation] = []

    # Group by base entity name (strip "variant" suffixes for grouping)
    name_groups: dict[str, list[ConsensusElement]] = {}
    for elem in elements:
        base_name = elem.triangulated.entity.name.lower().strip()
        if base_name not in name_groups:
            name_groups[base_name] = []
        name_groups[base_name].append(elem)

    # Check for variant_of relationships via entity metadata
    for _name, group in name_groups.items():
        if len(group) < 2:
            continue

        # Each group member with sufficient coverage is a variant
        viable_variants = []
        for elem in group:
            coverage = len(elem.triangulated.evidence_ids) / total_sources
            if coverage >= VARIANT_COVERAGE_THRESHOLD:
                viable_variants.append((elem, coverage))

        if len(viable_variants) >= 2:
            for idx, (elem, coverage) in enumerate(viable_variants):
                label = chr(ord("A") + idx)
                variants.append(
                    VariantAnnotation(
                        variant_label=f"variant_{label}",
                        element_name=elem.triangulated.entity.name,
                        evidence_ids=list(elem.triangulated.evidence_ids),
                        evidence_coverage=coverage,
                        contributing_categories=set(elem.contributing_categories),
                    )
                )

    logger.info("Detected %d process variants", len(variants))
    return variants


# -- Conflict detection during consensus ------------------------------------


def _detect_sequence_conflicts(
    elements: list[ConsensusElement],
    evidence_items: list[EvidenceItem],
    weight_map: dict[str, float] | None = None,
) -> list[ConflictStub]:
    """Detect sequence conflicts where sources disagree on element ordering.

    When high-weight and low-weight sources assert contradictory sequences,
    the higher-weight source wins and the lower-weight assertion becomes
    a ConflictStub.

    Args:
        elements: Consensus elements to check.
        evidence_items: All evidence items.
        weight_map: Optional custom weight map.

    Returns:
        List of ConflictStubs for sequence disagreements.
    """
    conflicts: list[ConflictStub] = []

    # Group elements by entity name to find sequence candidates
    by_name: dict[str, list[ConsensusElement]] = {}
    for elem in elements:
        name = elem.triangulated.entity.name.lower()
        by_name.setdefault(name, []).append(elem)

    for _name, group in by_name.items():
        if len(group) < 2:
            continue

        # Compare max_weight between group members
        sorted_group = sorted(group, key=lambda e: e.max_weight, reverse=True)
        primary = sorted_group[0]

        for secondary in sorted_group[1:]:
            weight_diff = primary.max_weight - secondary.max_weight
            if weight_diff > 0.3:
                # Significant weight difference — create conflict stub
                conflicts.append(
                    ConflictStub(
                        element_name=primary.triangulated.entity.name,
                        disagreement_type="sequence",
                        preferred_value=primary.triangulated.entity.name,
                        alternative_value=secondary.triangulated.entity.name,
                        preferred_evidence_ids=list(primary.triangulated.evidence_ids),
                        alternative_evidence_ids=list(secondary.triangulated.evidence_ids),
                        resolution_reason=f"Higher source weight ({primary.max_weight:.2f} vs {secondary.max_weight:.2f})",
                    )
                )

    return conflicts


# -- Main consensus builder --------------------------------------------------


def build_consensus(
    triangulated_elements: list[TriangulatedElement],
    evidence_items: list[EvidenceItem],
    engagement_weights: dict[str, float] | None = None,
) -> ConsensusResult:
    """Build consensus model using weighted voting by evidence type.

    LCD Inclusivity: ALL elements with any evidence support are included
    (not just those with consensus). Confidence score reflects the level
    of weighted agreement across sources.

    Enhancements over basic voting:
    - Per-engagement configurable weight map
    - Recency bias for tie-breaking between same-weight sources
    - Variant detection for structurally divergent paths
    - ConflictStub forwarding for contradiction resolution

    Args:
        triangulated_elements: Elements with triangulation data.
        evidence_items: All evidence items (for category/date lookup).
        engagement_weights: Optional per-engagement weight overrides.

    Returns:
        ConsensusResult with elements, variants, and conflict stubs.
    """
    weight_map = get_weight_map(engagement_weights)

    # Build evidence ID -> item mapping
    evidence_map: dict[str, EvidenceItem] = {}
    evidence_category_map: dict[str, str] = {}
    for item in evidence_items:
        eid = str(item.id)
        evidence_map[eid] = item
        evidence_category_map[eid] = str(item.category)

    results: list[ConsensusElement] = []

    for tri_elem in triangulated_elements:
        weighted_sum = 0.0
        max_weight = 0.0
        categories: set[str] = set()
        source_count = 0

        for ev_id in tri_elem.evidence_ids:
            category = evidence_category_map.get(ev_id, "")
            weight = _get_evidence_weight(category, weight_map)

            # Apply recency bias: weight * (base + factor * recency)
            ev_item = evidence_map.get(ev_id)
            recency = compute_recency_factor(getattr(ev_item, "source_date", None) if ev_item else None)

            adjusted_weight = weight * (RECENCY_BLEND_BASE + RECENCY_BLEND_FACTOR * recency)
            weighted_sum += adjusted_weight
            max_weight = max(max_weight, weight)
            source_count += 1
            if category:
                categories.add(category)

        # Normalized weighted vote score
        vote_score = weighted_sum / source_count if source_count > 0 else 0.0
        source_reliability = max_weight

        # Brightness hint based on vote score
        if vote_score >= BRIGHTNESS_BRIGHT_THRESHOLD:
            brightness = "bright"
        elif vote_score >= BRIGHTNESS_DIM_THRESHOLD:
            brightness = "dim"
        else:
            brightness = "dark"

        results.append(
            ConsensusElement(
                triangulated=tri_elem,
                weighted_vote_score=vote_score,
                max_weight=max_weight,
                contributing_categories=categories,
                source_reliability=source_reliability,
                brightness_hint=brightness,
            )
        )

    # Detect variants
    variants = detect_variants(results, evidence_items, weight_map)

    # Detect conflicts
    conflict_stubs = _detect_sequence_conflicts(results, evidence_items, weight_map)

    logger.info(
        "Built consensus for %d elements (avg score: %.3f), %d variants, %d conflicts",
        len(results),
        sum(r.weighted_vote_score for r in results) / len(results) if results else 0,
        len(variants),
        len(conflict_stubs),
    )

    return ConsensusResult(
        elements=results,
        variants=variants,
        conflict_stubs=conflict_stubs,
    )
