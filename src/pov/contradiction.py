"""Contradiction resolution for the LCD algorithm.

Step 8 of the 8-step LCD algorithm: Resolves conflicts forwarded from
consensus building (Step 6-7) using a three-way distinction classifier:

1. Naming Variant — Entity names resolve to the same canonical seed term
   (edit distance ≤ 2). Both evidence links preserved on merged entity.
2. Temporal Shift — Same entity asserted differently across time periods.
   Bitemporal validity stamps applied; no ConflictObject created.
3. Genuine Disagreement — Irreconcilable conflict. ConflictObject created
   with EpistemicFrames preserving both views for SME validation.

Severity scoring combines mismatch type criticality with source weight
differential. Six mismatch types from PRD Section 6.10.5 are handled.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from src.core.models import EvidenceItem
from src.core.models.conflict import ResolutionType
from src.pov.consensus import ConflictStub
from src.pov.constants import EVIDENCE_TYPE_WEIGHTS

logger = logging.getLogger(__name__)


# -- Severity scoring --------------------------------------------------------

MISMATCH_CRITICALITY: dict[str, float] = {
    "sequence_mismatch": 1.0,
    "existence_mismatch": 0.8,
    "rule_mismatch": 0.7,
    "io_mismatch": 0.6,
    "role_mismatch": 0.5,
    "control_gap": 0.4,
}


def compute_severity(
    mismatch_type: str,
    weight_a: float,
    weight_b: float,
) -> float:
    """Compute conflict severity from type criticality and weight differential.

    Severity = criticality * 0.6 + weight_differential * 0.4.
    Higher criticality types (sequence > existence > rule) and larger
    weight differentials produce higher severity scores.

    Args:
        mismatch_type: The MismatchType value string.
        weight_a: Source weight for the preferred view.
        weight_b: Source weight for the alternative view.

    Returns:
        Severity score between 0.0 and 1.0.
    """
    criticality = MISMATCH_CRITICALITY.get(mismatch_type, 0.5)
    if mismatch_type not in MISMATCH_CRITICALITY:
        logger.warning("Unknown mismatch type %r, using default criticality 0.5", mismatch_type)
    weight_diff = abs(weight_a - weight_b)
    severity = criticality * 0.6 + weight_diff * 0.4
    return max(0.0, min(1.0, severity))


# -- Edit distance for naming variant detection ------------------------------


def _edit_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings.

    Uses the standard dynamic programming algorithm. Case-insensitive.

    Args:
        s1: First string.
        s2: Second string.

    Returns:
        Minimum number of single-character edits (insert, delete, substitute).
    """
    s1 = s1.lower().strip()
    s2 = s2.lower().strip()

    if len(s1) < len(s2):
        return _edit_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # insertions, deletions, substitutions
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


# -- Three-way distinction dataclasses --------------------------------------


@dataclass
class NamingResolution:
    """Result of resolving a naming variant.

    Both raw terms map to the same canonical seed term. Entities are merged;
    no ConflictObject is created.

    Attributes:
        entity_name_a: First entity name.
        entity_name_b: Second entity name.
        canonical_term: The seed list canonical term.
        merged_evidence_ids: Combined evidence IDs from both entities.
    """

    entity_name_a: str = ""
    entity_name_b: str = ""
    canonical_term: str = ""
    merged_evidence_ids: list[str] = field(default_factory=list)


@dataclass
class TemporalResolution:
    """Result of resolving a temporal shift.

    Assertions are stamped with bitemporal validity; no ConflictObject created.

    Attributes:
        element_name: The element with temporal shift.
        older_value: The assertion from the older source.
        newer_value: The assertion from the newer source.
        older_valid_to: Inferred end of validity for the older assertion.
        newer_valid_from: Inferred start of validity for the newer assertion.
        older_evidence_ids: Evidence supporting the older assertion.
        newer_evidence_ids: Evidence supporting the newer assertion.
    """

    element_name: str = ""
    older_value: str = ""
    newer_value: str = ""
    older_valid_to: int | None = None  # Year
    newer_valid_from: int | None = None  # Year
    older_evidence_ids: list[str] = field(default_factory=list)
    newer_evidence_ids: list[str] = field(default_factory=list)


@dataclass
class GenuineDisagreement:
    """A genuine disagreement preserved with epistemic frames.

    Both views are retained; a ConflictObject is created for SME validation.

    Attributes:
        element_name: The element with genuine disagreement.
        mismatch_type: The type of mismatch.
        severity: Computed severity score.
        preferred_value: The value from the higher-weight source.
        alternative_value: The value from the lower-weight source.
        preferred_evidence_ids: Evidence supporting preferred view.
        alternative_evidence_ids: Evidence supporting alternative view.
        preferred_authority: Authority scope for preferred view's frame.
        alternative_authority: Authority scope for alternative view's frame.
        preferred_frame_kind: Epistemic frame kind for preferred view.
        alternative_frame_kind: Epistemic frame kind for alternative view.
        resolution_reason: Why this was classified as genuine disagreement.
        needs_sme_validation: Whether flagged for SME review.
    """

    element_name: str = ""
    mismatch_type: str = ""
    severity: float = 0.5
    preferred_value: str = ""
    alternative_value: str = ""
    preferred_evidence_ids: list[str] = field(default_factory=list)
    alternative_evidence_ids: list[str] = field(default_factory=list)
    preferred_authority: str = "system_telemetry"
    alternative_authority: str = "subject_matter_expert"
    preferred_frame_kind: str = "telemetric"
    alternative_frame_kind: str = "experiential"
    resolution_reason: str = ""
    needs_sme_validation: bool = True


@dataclass
class ContradictionResolutionResult:
    """Complete output from contradiction resolution.

    Attributes:
        naming_resolutions: Conflicts resolved as naming variants.
        temporal_resolutions: Conflicts resolved as temporal shifts.
        genuine_disagreements: Irreconcilable conflicts with ConflictObjects.
    """

    naming_resolutions: list[NamingResolution] = field(default_factory=list)
    temporal_resolutions: list[TemporalResolution] = field(default_factory=list)
    genuine_disagreements: list[GenuineDisagreement] = field(default_factory=list)

    @property
    def total_resolved(self) -> int:
        """Total number of conflicts resolved (naming + temporal)."""
        return len(self.naming_resolutions) + len(self.temporal_resolutions)

    @property
    def total_unresolved(self) -> int:
        """Number of genuine disagreements requiring SME validation."""
        return len(self.genuine_disagreements)


# -- Evidence category → authority scope mapping -----------------------------

CATEGORY_TO_AUTHORITY: dict[str, str] = {
    "structured_data": "system_telemetry",
    "task_mining": "task_mining_agent",
    "bpm_process_models": "process_owner",
    "documents": "business_analyst",
    "controls_evidence": "compliance_officer",
    "regulatory_policy": "external_auditor",
    "saas_exports": "system_administrator",
    "domain_communications": "operations_team",
    "images": "operations_team",
    "audio": "subject_matter_expert",
    "video": "subject_matter_expert",
    "km4work": "survey_respondent",
    "job_aids_edge_cases": "operations_team",
}

CATEGORY_TO_FRAME_KIND: dict[str, str] = {
    "structured_data": "telemetric",
    "task_mining": "behavioral",
    "bpm_process_models": "procedural",
    "documents": "procedural",
    "controls_evidence": "regulatory",
    "regulatory_policy": "regulatory",
    "saas_exports": "telemetric",
    "domain_communications": "experiential",
    "images": "experiential",
    "audio": "elicited",
    "video": "elicited",
    "km4work": "elicited",
    "job_aids_edge_cases": "experiential",
}


# -- Naming variant detection ------------------------------------------------


def detect_naming_variant(
    name_a: str,
    name_b: str,
    seed_terms: list[str],
    max_edit_distance: int = 2,
) -> str | None:
    """Check if two entity names are naming variants of the same seed term.

    Both names must be within max_edit_distance of the same canonical
    seed term. Returns the canonical term if matched, None otherwise.

    Args:
        name_a: First entity name.
        name_b: Second entity name.
        seed_terms: Canonical terms from the engagement seed list.
        max_edit_distance: Maximum Levenshtein distance for a match.

    Returns:
        The canonical seed term if both names match, None otherwise.
    """
    for seed in seed_terms:
        dist_a = _edit_distance(name_a, seed)
        dist_b = _edit_distance(name_b, seed)
        if dist_a <= max_edit_distance and dist_b <= max_edit_distance:
            return seed
    return None


# -- Temporal shift detection ------------------------------------------------


def detect_temporal_shift(
    evidence_a: EvidenceItem | None,
    evidence_b: EvidenceItem | None,
    min_year_gap: int = 2,
) -> bool:
    """Check if two evidence items represent a temporal shift.

    A temporal shift is detected when both sources are high-quality
    documents with a significant time gap between them.

    Args:
        evidence_a: First evidence item.
        evidence_b: Second evidence item.
        min_year_gap: Minimum years between sources for temporal shift.

    Returns:
        True if temporal shift detected.
    """
    if evidence_a is None or evidence_b is None:
        return False

    date_a = getattr(evidence_a, "source_date", None)
    date_b = getattr(evidence_b, "source_date", None)

    if date_a is None or date_b is None:
        return False

    # Both must be document-class evidence (process docs, regulatory, etc.)
    doc_categories = {
        "documents",
        "bpm_process_models",
        "controls_evidence",
        "regulatory_policy",
    }
    cat_a = str(evidence_a.category)
    cat_b = str(evidence_b.category)

    if cat_a not in doc_categories or cat_b not in doc_categories:
        return False

    # Check year gap
    year_a = date_a.year if isinstance(date_a, datetime) else 0
    year_b = date_b.year if isinstance(date_b, datetime) else 0
    year_gap = abs(year_a - year_b)

    return year_gap >= min_year_gap


# -- Three-way distinction classifier ----------------------------------------


def classify_conflict(
    stub: ConflictStub,
    evidence_map: dict[str, EvidenceItem],
    seed_terms: list[str],
) -> str:
    """Classify a conflict stub using the three-way distinction.

    Order of checks:
    1. Naming variant (edit distance to seed terms)
    2. Temporal shift (date gap between document-class sources)
    3. Genuine disagreement (default fallback)

    Args:
        stub: The conflict stub from consensus building.
        evidence_map: Evidence ID → EvidenceItem mapping.
        seed_terms: Canonical terms from the engagement seed list.

    Returns:
        One of: "naming_variant", "temporal_shift", "genuine_disagreement".
    """
    # 1. Check naming variant
    if stub.preferred_value and stub.alternative_value:
        canonical = detect_naming_variant(stub.preferred_value, stub.alternative_value, seed_terms)
        if canonical is not None:
            return ResolutionType.NAMING_VARIANT.value

    # 2. Check temporal shift — need representative evidence from each side
    pref_evidence = _get_representative_evidence(stub.preferred_evidence_ids, evidence_map)
    alt_evidence = _get_representative_evidence(stub.alternative_evidence_ids, evidence_map)

    if detect_temporal_shift(pref_evidence, alt_evidence):
        return ResolutionType.TEMPORAL_SHIFT.value

    # 3. Default: genuine disagreement
    return ResolutionType.GENUINE_DISAGREEMENT.value


def _get_representative_evidence(
    evidence_ids: list[str],
    evidence_map: dict[str, EvidenceItem],
) -> EvidenceItem | None:
    """Get the highest-weight evidence item from a list of IDs.

    Args:
        evidence_ids: List of evidence item IDs.
        evidence_map: Evidence ID → EvidenceItem mapping.

    Returns:
        The evidence item with highest type weight, or None.
    """
    best: EvidenceItem | None = None
    best_weight = -1.0

    for eid in evidence_ids:
        item = evidence_map.get(eid)
        if item is None:
            continue
        weight = EVIDENCE_TYPE_WEIGHTS.get(str(item.category), 0.3)
        if weight > best_weight:
            best_weight = weight
            best = item

    return best


def _get_evidence_weight(evidence_id: str, evidence_map: dict[str, EvidenceItem]) -> float:
    """Get the type weight for an evidence item.

    Args:
        evidence_id: The evidence item ID.
        evidence_map: Evidence ID → EvidenceItem mapping.

    Returns:
        Weight between 0.0 and 1.0.
    """
    item = evidence_map.get(evidence_id)
    if item is None:
        return 0.3
    return EVIDENCE_TYPE_WEIGHTS.get(str(item.category), 0.3)


def _get_evidence_category(evidence_id: str, evidence_map: dict[str, EvidenceItem]) -> str:
    """Get the category for an evidence item.

    Args:
        evidence_id: The evidence item ID.
        evidence_map: Evidence ID → EvidenceItem mapping.

    Returns:
        Category string.
    """
    item = evidence_map.get(evidence_id)
    if item is None:
        return ""
    return str(item.category)


# -- Resolution builders -----------------------------------------------------


def _resolve_as_naming_variant(
    stub: ConflictStub,
    seed_terms: list[str],
) -> NamingResolution:
    """Build a NamingResolution from a conflict stub.

    Args:
        stub: The conflict stub classified as naming variant.
        seed_terms: Canonical terms from the engagement seed list.

    Returns:
        NamingResolution with merged evidence.
    """
    canonical = detect_naming_variant(stub.preferred_value, stub.alternative_value, seed_terms)
    merged_ids = list(set(stub.preferred_evidence_ids + stub.alternative_evidence_ids))

    return NamingResolution(
        entity_name_a=stub.preferred_value,
        entity_name_b=stub.alternative_value,
        canonical_term=canonical or stub.preferred_value,
        merged_evidence_ids=merged_ids,
    )


def _resolve_as_temporal_shift(
    stub: ConflictStub,
    evidence_map: dict[str, EvidenceItem],
) -> TemporalResolution:
    """Build a TemporalResolution with bitemporal validity stamps.

    The older source gets a valid_to inferred as one year before the newer
    source date. The newer source gets valid_from as its source year.

    Args:
        stub: The conflict stub classified as temporal shift.
        evidence_map: Evidence ID → EvidenceItem mapping.

    Returns:
        TemporalResolution with bitemporal stamps.
    """
    pref_ev = _get_representative_evidence(stub.preferred_evidence_ids, evidence_map)
    alt_ev = _get_representative_evidence(stub.alternative_evidence_ids, evidence_map)

    pref_date = getattr(pref_ev, "source_date", None) if pref_ev else None
    alt_date = getattr(alt_ev, "source_date", None) if alt_ev else None

    pref_year = pref_date.year if isinstance(pref_date, datetime) else None
    alt_year = alt_date.year if isinstance(alt_date, datetime) else None

    # Determine which is older / newer
    if pref_year and alt_year:
        if pref_year <= alt_year:
            older_value, newer_value = stub.preferred_value, stub.alternative_value
            _older_year, newer_year = pref_year, alt_year
            older_ids = stub.preferred_evidence_ids
            newer_ids = stub.alternative_evidence_ids
        else:
            older_value, newer_value = stub.alternative_value, stub.preferred_value
            _older_year, newer_year = alt_year, pref_year
            older_ids = stub.alternative_evidence_ids
            newer_ids = stub.preferred_evidence_ids
    else:
        # Fallback: preferred = newer, alternative = older
        older_value, newer_value = stub.alternative_value, stub.preferred_value
        newer_year = pref_year
        older_ids = stub.alternative_evidence_ids
        newer_ids = stub.preferred_evidence_ids

    # Infer validity boundary: older valid_to = newer_year - 1
    older_valid_to = newer_year - 1 if newer_year else None

    return TemporalResolution(
        element_name=stub.element_name,
        older_value=older_value,
        newer_value=newer_value,
        older_valid_to=older_valid_to,
        newer_valid_from=newer_year,
        older_evidence_ids=list(older_ids),
        newer_evidence_ids=list(newer_ids),
    )


def _resolve_as_genuine_disagreement(
    stub: ConflictStub,
    evidence_map: dict[str, EvidenceItem],
) -> GenuineDisagreement:
    """Build a GenuineDisagreement with epistemic frame data.

    Creates frame metadata for both the preferred and alternative views,
    mapping evidence categories to authority scopes and frame kinds.

    Args:
        stub: The conflict stub classified as genuine disagreement.
        evidence_map: Evidence ID → EvidenceItem mapping.

    Returns:
        GenuineDisagreement with epistemic frame annotations.
    """
    # Get weights for severity computation
    pref_weight = max(
        (_get_evidence_weight(eid, evidence_map) for eid in stub.preferred_evidence_ids),
        default=0.3,
    )
    alt_weight = max(
        (_get_evidence_weight(eid, evidence_map) for eid in stub.alternative_evidence_ids),
        default=0.3,
    )

    severity = compute_severity(stub.disagreement_type, pref_weight, alt_weight)

    # Determine epistemic frame metadata from representative evidence
    pref_ev = _get_representative_evidence(stub.preferred_evidence_ids, evidence_map)
    alt_ev = _get_representative_evidence(stub.alternative_evidence_ids, evidence_map)
    pref_cat = str(pref_ev.category) if pref_ev else ""
    alt_cat = str(alt_ev.category) if alt_ev else ""

    return GenuineDisagreement(
        element_name=stub.element_name,
        mismatch_type=stub.disagreement_type,
        severity=severity,
        preferred_value=stub.preferred_value,
        alternative_value=stub.alternative_value,
        preferred_evidence_ids=list(stub.preferred_evidence_ids),
        alternative_evidence_ids=list(stub.alternative_evidence_ids),
        preferred_authority=CATEGORY_TO_AUTHORITY.get(pref_cat, "operations_team"),
        alternative_authority=CATEGORY_TO_AUTHORITY.get(alt_cat, "subject_matter_expert"),
        preferred_frame_kind=CATEGORY_TO_FRAME_KIND.get(pref_cat, "procedural"),
        alternative_frame_kind=CATEGORY_TO_FRAME_KIND.get(alt_cat, "experiential"),
        resolution_reason=(
            f"Cannot be explained by naming variance or temporal shift. "
            f"Weight differential: {abs(pref_weight - alt_weight):.2f}"
        ),
        needs_sme_validation=True,
    )


# -- Main resolver -----------------------------------------------------------


def resolve_contradictions(
    conflict_stubs: list[ConflictStub],
    evidence_items: list[EvidenceItem],
    seed_terms: list[str] | None = None,
) -> ContradictionResolutionResult:
    """Resolve contradictions using the three-way distinction classifier.

    For each conflict stub from consensus building, classifies the conflict as:
    1. Naming variant → merge entities, no ConflictObject
    2. Temporal shift → apply bitemporal validity, no ConflictObject
    3. Genuine disagreement → create ConflictObject + EpistemicFrames

    Args:
        conflict_stubs: Conflict stubs forwarded from consensus building.
        evidence_items: All evidence items for the engagement.
        seed_terms: Canonical terms from the engagement seed list.

    Returns:
        ContradictionResolutionResult with categorized resolutions.
    """
    if seed_terms is None:
        seed_terms = []

    # Build evidence lookup
    evidence_map: dict[str, EvidenceItem] = {}
    for item in evidence_items:
        evidence_map[str(item.id)] = item

    result = ContradictionResolutionResult()

    for stub in conflict_stubs:
        classification = classify_conflict(stub, evidence_map, seed_terms)

        if classification == ResolutionType.NAMING_VARIANT.value:
            resolution = _resolve_as_naming_variant(stub, seed_terms)
            result.naming_resolutions.append(resolution)
            logger.info(
                "Naming variant resolved: %r + %r → %r",
                resolution.entity_name_a,
                resolution.entity_name_b,
                resolution.canonical_term,
            )

        elif classification == ResolutionType.TEMPORAL_SHIFT.value:
            resolution = _resolve_as_temporal_shift(stub, evidence_map)
            result.temporal_resolutions.append(resolution)
            logger.info(
                "Temporal shift resolved: %r (valid_to=%s) → %r (valid_from=%s)",
                resolution.older_value,
                resolution.older_valid_to,
                resolution.newer_value,
                resolution.newer_valid_from,
            )

        else:
            disagreement = _resolve_as_genuine_disagreement(stub, evidence_map)
            result.genuine_disagreements.append(disagreement)
            logger.info(
                "Genuine disagreement: %r (%s, severity=%.2f) — flagged for SME",
                disagreement.element_name,
                disagreement.mismatch_type,
                disagreement.severity,
            )

    logger.info(
        "Resolved %d contradictions: %d naming variants, %d temporal shifts, %d genuine disagreements",
        len(conflict_stubs),
        len(result.naming_resolutions),
        len(result.temporal_resolutions),
        len(result.genuine_disagreements),
    )

    return result


# -- Backward-compatible persistence bridge -----------------------------------


@dataclass
class DetectedContradiction:
    """Flat contradiction record for database persistence.

    Maps the three-way resolution result types into the Contradiction ORM
    model's column schema (element_name, field_name, values, resolution_value,
    resolution_reason, evidence_ids).
    """

    element_name: str = ""
    field_name: str = ""
    values: list[dict[str, str]] = field(default_factory=list)
    resolution_value: str = ""
    resolution_reason: str = ""
    evidence_ids: list[str] = field(default_factory=list)


def flatten_to_detected_contradictions(
    result: ContradictionResolutionResult,
) -> list[DetectedContradiction]:
    """Convert three-way resolution results to flat persistence records.

    Each NamingResolution, TemporalResolution, and GenuineDisagreement
    is mapped to a DetectedContradiction for database persistence via
    the Contradiction ORM model.

    Args:
        result: Output from resolve_contradictions.

    Returns:
        List of DetectedContradiction records ready for persistence.
    """
    records: list[DetectedContradiction] = []

    for nr in result.naming_resolutions:
        records.append(
            DetectedContradiction(
                element_name=nr.canonical_term,
                field_name="naming_variant",
                values=[
                    {"name_a": nr.entity_name_a, "name_b": nr.entity_name_b},
                ],
                resolution_value=nr.canonical_term,
                resolution_reason=f"Merged as naming variant of seed term '{nr.canonical_term}'",
                evidence_ids=nr.merged_evidence_ids,
            )
        )

    for tr in result.temporal_resolutions:
        records.append(
            DetectedContradiction(
                element_name=tr.element_name,
                field_name="temporal_shift",
                values=[
                    {"older": tr.older_value, "newer": tr.newer_value},
                ],
                resolution_value=tr.newer_value,
                resolution_reason=(
                    f"Temporal shift resolved: older valid_to={tr.older_valid_to}, "
                    f"newer valid_from={tr.newer_valid_from}"
                ),
                evidence_ids=tr.older_evidence_ids + tr.newer_evidence_ids,
            )
        )

    for gd in result.genuine_disagreements:
        records.append(
            DetectedContradiction(
                element_name=gd.element_name,
                field_name=gd.mismatch_type,
                values=[
                    {"preferred": gd.preferred_value, "alternative": gd.alternative_value},
                ],
                resolution_value=gd.preferred_value,
                resolution_reason=gd.resolution_reason,
                evidence_ids=gd.preferred_evidence_ids + gd.alternative_evidence_ids,
            )
        )

    return records
