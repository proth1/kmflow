"""Proactive evidence gap identification agent.

Scans engagements for missing evidence, weak coverage areas,
and stale data to generate actionable recommendations.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def scan_evidence_gaps(
    evidence_items: list[dict[str, Any]],
    process_elements: list[dict[str, Any]],
    shelf_requests: list[dict[str, Any]] | None = None,
    coverage_threshold: float = 0.6,
) -> list[dict[str, Any]]:
    """Scan for evidence gaps across an engagement.

    Args:
        evidence_items: Current evidence items with categories and scores.
        process_elements: Process elements that need evidence support.
        shelf_requests: Existing shelf data requests.
        coverage_threshold: Minimum coverage score to not flag as gap.

    Returns:
        List of identified gaps with severity and recommendations.
    """
    gaps: list[dict[str, Any]] = []

    # Check for unsupported process elements
    evidence_ids = {str(e.get("id", "")) for e in evidence_items}
    for element in process_elements:
        element_evidence = element.get("evidence_ids", []) or []
        supported_count = sum(1 for eid in element_evidence if eid in evidence_ids)

        if supported_count == 0:
            gaps.append(
                {
                    "gap_type": "missing_evidence",
                    "severity": "high",
                    "element_name": element.get("name", "Unknown"),
                    "element_id": str(element.get("id", "")),
                    "description": f"No evidence supports element '{element.get('name', 'Unknown')}'",
                    "recommendation": f"Collect evidence for '{element.get('name', 'Unknown')}'",
                }
            )
        elif supported_count == 1:
            gaps.append(
                {
                    "gap_type": "single_source",
                    "severity": "medium",
                    "element_name": element.get("name", "Unknown"),
                    "element_id": str(element.get("id", "")),
                    "description": (
                        f"Only one evidence source for '{element.get('name', 'Unknown')}' - triangulation not possible"
                    ),
                    "recommendation": f"Add corroborating evidence for '{element.get('name', 'Unknown')}'",
                }
            )

    # Check for low quality evidence
    for item in evidence_items:
        quality = item.get("quality_score", 0)
        if quality < coverage_threshold:
            gaps.append(
                {
                    "gap_type": "weak_evidence",
                    "severity": "medium",
                    "element_name": item.get("name", "Unknown"),
                    "element_id": str(item.get("id", "")),
                    "description": f"Low quality evidence: '{item.get('name', '')}' (score: {quality:.2f})",
                    "recommendation": f"Improve or replace evidence '{item.get('name', '')}'",
                }
            )

    # Check for category coverage gaps
    categories_present = {e.get("category") for e in evidence_items}
    expected_categories = {
        "documents",
        "structured_data",
        "bpm_process_models",
        "controls_evidence",
        "domain_communications",
    }
    missing_categories = expected_categories - categories_present
    for cat in missing_categories:
        gaps.append(
            {
                "gap_type": "missing_category",
                "severity": "low",
                "element_name": cat,
                "element_id": None,
                "description": f"No evidence in category: {cat}",
                "recommendation": f"Collect {cat.replace('_', ' ')} evidence",
            }
        )

    # Check for stale evidence
    now = datetime.now(UTC)
    for item in evidence_items:
        source_date = item.get("source_date")
        if source_date:
            if isinstance(source_date, str):
                try:
                    source_date = datetime.fromisoformat(source_date)
                except ValueError:
                    continue
            if hasattr(source_date, "year") and (now.year - source_date.year) > 1:
                gaps.append(
                    {
                        "gap_type": "stale_evidence",
                        "severity": "medium",
                        "element_name": item.get("name", "Unknown"),
                        "element_id": str(item.get("id", "")),
                        "description": f"Evidence '{item.get('name', '')}' is over a year old",
                        "recommendation": f"Request updated version of '{item.get('name', '')}'",
                    }
                )

    return gaps
