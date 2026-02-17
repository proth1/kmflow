"""Evidence gap detection for the LCD algorithm.

Step 8: Identifies missing evidence, weak coverage, and single-source
elements to highlight areas needing additional evidence collection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.core.models import (
    EvidenceCategory,
    EvidenceItem,
    GapSeverity,
    GapType,
)
from src.pov.consensus import ConsensusElement

logger = logging.getLogger(__name__)


@dataclass
class DetectedGap:
    """An evidence gap identified during POV generation.

    Attributes:
        gap_type: Type of gap (MISSING_DATA, WEAK_EVIDENCE, SINGLE_SOURCE).
        description: Human-readable description of the gap.
        severity: Severity level (HIGH, MEDIUM, LOW).
        recommendation: Suggested action to address the gap.
        related_element_name: Name of the related process element (if any).
    """

    gap_type: GapType = GapType.MISSING_DATA
    description: str = ""
    severity: GapSeverity = GapSeverity.MEDIUM
    recommendation: str = ""
    related_element_name: str | None = None


def _detect_single_source_gaps(
    consensus_elements: list[ConsensusElement],
) -> list[DetectedGap]:
    """Detect elements supported by only a single evidence source.

    Args:
        consensus_elements: Elements with consensus data.

    Returns:
        List of single-source gap detections.
    """
    gaps: list[DetectedGap] = []

    for elem in consensus_elements:
        if elem.triangulated.source_count == 1:
            entity_name = elem.triangulated.entity.name
            entity_type = elem.triangulated.entity.entity_type
            gaps.append(
                DetectedGap(
                    gap_type=GapType.SINGLE_SOURCE,
                    description=(
                        f"{entity_type.capitalize()} '{entity_name}' is supported by only one evidence source"
                    ),
                    severity=GapSeverity.MEDIUM,
                    recommendation=(
                        f"Collect additional evidence to corroborate '{entity_name}'. "
                        f"Look for references in process documentation, interviews, "
                        f"or system data."
                    ),
                    related_element_name=entity_name,
                )
            )

    return gaps


def _detect_weak_evidence_gaps(
    scored_elements: list[tuple[ConsensusElement, float, str]],
) -> list[DetectedGap]:
    """Detect elements with weak confidence scores.

    Args:
        scored_elements: Elements with confidence scores and levels.

    Returns:
        List of weak evidence gap detections.
    """
    gaps: list[DetectedGap] = []

    for elem, score, level in scored_elements:
        if level in ("LOW", "VERY_LOW"):
            entity_name = elem.triangulated.entity.name
            severity = GapSeverity.HIGH if level == "VERY_LOW" else GapSeverity.MEDIUM
            gaps.append(
                DetectedGap(
                    gap_type=GapType.WEAK_EVIDENCE,
                    description=(f"Element '{entity_name}' has {level} confidence (score: {score:.2f})"),
                    severity=severity,
                    recommendation=(
                        f"Strengthen evidence for '{entity_name}' by collecting "
                        f"higher-quality sources (structured data, BPM models, "
                        f"or official documents)."
                    ),
                    related_element_name=entity_name,
                )
            )

    return gaps


def _detect_missing_category_gaps(
    evidence_items: list[EvidenceItem],
) -> list[DetectedGap]:
    """Detect evidence categories with no evidence items.

    Args:
        evidence_items: All evidence items in the engagement.

    Returns:
        List of missing category gap detections.
    """
    covered_categories = {str(item.category) for item in evidence_items}
    all_categories = {cat.value for cat in EvidenceCategory}
    missing = all_categories - covered_categories

    # Prioritize critical missing categories
    critical_categories = {
        "structured_data",
        "bpm_process_models",
        "documents",
        "controls_evidence",
    }

    gaps: list[DetectedGap] = []
    for category in sorted(missing):
        is_critical = category in critical_categories
        gaps.append(
            DetectedGap(
                gap_type=GapType.MISSING_DATA,
                description=f"No evidence collected for category: {category}",
                severity=GapSeverity.HIGH if is_critical else GapSeverity.LOW,
                recommendation=(
                    f"Request '{category}' evidence from the client. "
                    f"This category is {'critical for process analysis' if is_critical else 'supplementary'}."
                ),
            )
        )

    return gaps


def detect_gaps(
    consensus_elements: list[ConsensusElement],
    scored_elements: list[tuple[ConsensusElement, float, str]],
    evidence_items: list[EvidenceItem],
) -> list[DetectedGap]:
    """Run all gap detection checks.

    Combines single-source, weak-evidence, and missing-category detections.

    Args:
        consensus_elements: Elements with consensus data.
        scored_elements: Elements with confidence scores.
        evidence_items: All evidence items in the engagement.

    Returns:
        Combined list of all detected gaps.
    """
    gaps: list[DetectedGap] = []

    gaps.extend(_detect_single_source_gaps(consensus_elements))
    gaps.extend(_detect_weak_evidence_gaps(scored_elements))
    gaps.extend(_detect_missing_category_gaps(evidence_items))

    logger.info(
        "Detected %d gaps: %d single-source, %d weak-evidence, %d missing-data",
        len(gaps),
        sum(1 for g in gaps if g.gap_type == GapType.SINGLE_SOURCE),
        sum(1 for g in gaps if g.gap_type == GapType.WEAK_EVIDENCE),
        sum(1 for g in gaps if g.gap_type == GapType.MISSING_DATA),
    )

    return gaps
