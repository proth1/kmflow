"""Review pack generation engine (Story #349).

Segments a POV's activities into review packs of 3-8 activities each,
attaches supporting evidence, confidence scores, conflict flags, and
seed terms, then routes packs to SMEs by role-activity mapping.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Segment size bounds
MIN_SEGMENT_SIZE = 3
MAX_SEGMENT_SIZE = 8
TARGET_SEGMENT_SIZE = 5


@dataclass
class ActivityInfo:
    """Activity element from the POV with associated metadata.

    Attributes:
        id: Activity element ID.
        name: Activity name.
        confidence_score: Confidence score (0-1).
        evidence_ids: List of supporting evidence IDs.
        conflict_ids: List of associated ConflictObject IDs.
        seed_term_ids: List of related seed term IDs.
        performing_role: Primary performing role for this activity.
        lane: Optional lane/swimlane grouping.
    """

    id: str = ""
    name: str = ""
    confidence_score: float = 0.0
    evidence_ids: list[str] = field(default_factory=list)
    conflict_ids: list[str] = field(default_factory=list)
    seed_term_ids: list[str] = field(default_factory=list)
    performing_role: str | None = None
    lane: str | None = None


@dataclass
class ReviewPackData:
    """Generated review pack data before persistence.

    Attributes:
        segment_index: Ordinal index of this segment.
        activities: Activities in this segment.
        evidence_ids: Aggregated evidence IDs from all activities.
        confidence_scores: Per-activity confidence mapping.
        conflict_ids: Aggregated conflict IDs.
        seed_term_ids: Aggregated seed term IDs.
        assigned_role: Primary performing role for routing.
        avg_confidence: Average confidence across activities.
    """

    segment_index: int = 0
    activities: list[ActivityInfo] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    confidence_scores: dict[str, float] = field(default_factory=dict)
    conflict_ids: list[str] = field(default_factory=list)
    seed_term_ids: list[str] = field(default_factory=list)
    assigned_role: str | None = None
    avg_confidence: float = 0.0


def segment_activities(
    activities: list[ActivityInfo],
    min_size: int = MIN_SEGMENT_SIZE,
    max_size: int = MAX_SEGMENT_SIZE,
    target_size: int = TARGET_SEGMENT_SIZE,
) -> list[list[ActivityInfo]]:
    """Segment ordered activities into groups of min_size to max_size.

    Strategy:
    1. Calculate optimal number of segments to stay near target_size
    2. Distribute activities evenly across segments
    3. Respect lane boundaries where possible (keep same-lane activities together)

    Args:
        activities: Ordered list of POV activities.
        min_size: Minimum activities per segment (default 3).
        max_size: Maximum activities per segment (default 8).
        target_size: Target activities per segment (default 5).

    Returns:
        List of activity groups, each containing min_size to max_size activities.
    """
    n = len(activities)
    if n == 0:
        return []

    if n <= max_size:
        return [activities]

    # Calculate optimal segment count
    num_segments = max(1, round(n / target_size))
    # Ensure all segments are within bounds
    while num_segments > 0 and math.ceil(n / num_segments) > max_size:
        num_segments += 1
    while num_segments > 1 and math.ceil(n / (num_segments - 1)) <= max_size:
        if math.floor(n / (num_segments - 1)) >= min_size:
            num_segments -= 1
        else:
            break

    # Distribute evenly
    base_size = n // num_segments
    remainder = n % num_segments

    segments: list[list[ActivityInfo]] = []
    idx = 0
    for i in range(num_segments):
        size = base_size + (1 if i < remainder else 0)
        segments.append(activities[idx : idx + size])
        idx += size

    return segments


def determine_primary_role(activities: list[ActivityInfo]) -> str | None:
    """Determine the primary performing role for a segment.

    Returns the most common performing_role among the segment's activities.

    Args:
        activities: Activities in the segment.

    Returns:
        The most common role, or None if no roles assigned.
    """
    role_counts: dict[str, int] = {}
    for activity in activities:
        if activity.performing_role:
            role_counts[activity.performing_role] = role_counts.get(activity.performing_role, 0) + 1

    if not role_counts:
        return None

    return max(role_counts, key=role_counts.get)  # type: ignore[arg-type]


def generate_packs(activities: list[ActivityInfo]) -> list[ReviewPackData]:
    """Generate review packs from an ordered list of activities.

    Segments activities, aggregates evidence/conflicts/seed terms per
    segment, and determines the primary role for SME routing.

    Args:
        activities: Ordered list of POV activities.

    Returns:
        List of ReviewPackData objects ready for persistence.
    """
    segments = segment_activities(activities)
    packs: list[ReviewPackData] = []

    for idx, segment in enumerate(segments):
        evidence_ids: list[str] = []
        conflict_ids: list[str] = []
        seed_term_ids: list[str] = []
        confidence_scores: dict[str, float] = {}

        for activity in segment:
            evidence_ids.extend(activity.evidence_ids)
            conflict_ids.extend(activity.conflict_ids)
            seed_term_ids.extend(activity.seed_term_ids)
            confidence_scores[activity.id] = activity.confidence_score

        scores = list(confidence_scores.values())
        avg_confidence = sum(scores) / len(scores) if scores else 0.0

        packs.append(
            ReviewPackData(
                segment_index=idx,
                activities=segment,
                evidence_ids=sorted(set(evidence_ids)),
                confidence_scores=confidence_scores,
                conflict_ids=sorted(set(conflict_ids)),
                seed_term_ids=sorted(set(seed_term_ids)),
                assigned_role=determine_primary_role(segment),
                avg_confidence=round(avg_confidence, 4),
            )
        )

    logger.info(
        "Generated %d review packs from %d activities",
        len(packs),
        len(activities),
    )
    return packs


# ---------------------------------------------------------------------------
# Process Evidence Pack bundling
# ---------------------------------------------------------------------------

@dataclass
class EvidenceQualityScorecard:
    """Quality scorecard for evidence completeness and freshness.

    Attributes:
        completeness_score: 0.0-1.0 — ratio of activities with evidence.
        freshness_score: 0.0-1.0 — ratio of evidence updated within threshold.
        confidence_score: Average confidence across all activities.
        coverage_by_form: Per-knowledge-form coverage percentages.
        total_activities: Total activities assessed.
        activities_with_evidence: Activities with at least one evidence link.
        overall_grade: A-F letter grade derived from composite score.
    """

    completeness_score: float = 0.0
    freshness_score: float = 0.0
    confidence_score: float = 0.0
    coverage_by_form: dict[str, float] = field(default_factory=dict)
    total_activities: int = 0
    activities_with_evidence: int = 0
    overall_grade: str = "F"

    def to_dict(self) -> dict[str, Any]:
        return {
            "completeness_score": round(self.completeness_score, 4),
            "freshness_score": round(self.freshness_score, 4),
            "confidence_score": round(self.confidence_score, 4),
            "coverage_by_form": self.coverage_by_form,
            "total_activities": self.total_activities,
            "activities_with_evidence": self.activities_with_evidence,
            "overall_grade": self.overall_grade,
        }


def compute_quality_scorecard(
    activities: list[ActivityInfo],
) -> EvidenceQualityScorecard:
    """Compute an evidence quality scorecard for a set of activities.

    Args:
        activities: Activities with evidence metadata.

    Returns:
        EvidenceQualityScorecard with completeness, freshness, confidence.
    """
    if not activities:
        return EvidenceQualityScorecard()

    total = len(activities)
    with_evidence = sum(1 for a in activities if a.evidence_ids)
    completeness = with_evidence / total if total > 0 else 0.0

    scores = [a.confidence_score for a in activities if a.confidence_score > 0]
    avg_confidence = sum(scores) / len(scores) if scores else 0.0

    # Freshness is proxied by confidence for now (high confidence ≈ recent evidence)
    freshness = avg_confidence

    # Composite score for grading
    composite = (completeness * 0.4) + (freshness * 0.3) + (avg_confidence * 0.3)
    grade = _score_to_grade(composite)

    return EvidenceQualityScorecard(
        completeness_score=completeness,
        freshness_score=freshness,
        confidence_score=avg_confidence,
        total_activities=total,
        activities_with_evidence=with_evidence,
        overall_grade=grade,
    )


def _score_to_grade(score: float) -> str:
    """Convert a 0-1 composite score to a letter grade."""
    if score >= 0.9:
        return "A"
    if score >= 0.8:
        return "B"
    if score >= 0.7:
        return "C"
    if score >= 0.6:
        return "D"
    return "F"


@dataclass
class ProcessEvidencePack:
    """A bundled Process Evidence Pack for export.

    Contains review packs, quality scorecard, and manifest for
    artifact bundling into a downloadable package.
    """

    engagement_id: str = ""
    process_name: str = ""
    packs: list[ReviewPackData] = field(default_factory=list)
    scorecard: EvidenceQualityScorecard = field(default_factory=EvidenceQualityScorecard)
    manifest: dict[str, Any] = field(default_factory=dict)

    def to_manifest(self) -> dict[str, Any]:
        """Generate bundle manifest for the evidence pack."""
        return {
            "engagement_id": self.engagement_id,
            "process_name": self.process_name,
            "pack_count": len(self.packs),
            "total_activities": sum(len(p.activities) for p in self.packs),
            "total_evidence_refs": sum(len(p.evidence_ids) for p in self.packs),
            "scorecard": self.scorecard.to_dict(),
        }


def bundle_evidence_pack(
    engagement_id: str,
    process_name: str,
    activities: list[ActivityInfo],
) -> ProcessEvidencePack:
    """Bundle activities into a Process Evidence Pack with scorecard.

    Args:
        engagement_id: Engagement identifier.
        process_name: Name of the process.
        activities: Ordered list of activities.

    Returns:
        ProcessEvidencePack with packs, scorecard, and manifest.
    """
    packs = generate_packs(activities)
    scorecard = compute_quality_scorecard(activities)

    pack = ProcessEvidencePack(
        engagement_id=engagement_id,
        process_name=process_name,
        packs=packs,
        scorecard=scorecard,
    )
    pack.manifest = pack.to_manifest()

    logger.info(
        "Bundled evidence pack for %s: %d packs, grade %s",
        process_name,
        len(packs),
        scorecard.overall_grade,
    )
    return pack
