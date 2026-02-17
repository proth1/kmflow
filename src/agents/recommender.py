"""Recommendation generation from identified gaps.

Converts gap analysis results into actionable recommendations
and auto-generates ShelfDataRequest items.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def generate_recommendations(
    gaps: list[dict[str, Any]],
    existing_requests: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Generate prioritized recommendations from gaps.

    Args:
        gaps: List of identified gaps from gap_scanner.
        existing_requests: Already-created shelf data requests.

    Returns:
        Prioritized list of recommendations.
    """
    existing_items = set()
    if existing_requests:
        for req in existing_requests:
            for item in req.get("items", []):
                existing_items.add(item.get("item_name", "").lower())

    severity_order = {"high": 0, "medium": 1, "low": 2}
    sorted_gaps = sorted(gaps, key=lambda g: severity_order.get(g.get("severity", "low"), 3))

    recommendations: list[dict[str, Any]] = []
    for gap in sorted_gaps:
        rec_text = gap.get("recommendation", "")
        if rec_text.lower() in existing_items:
            continue

        recommendations.append({
            "gap_type": gap["gap_type"],
            "severity": gap["severity"],
            "recommendation": rec_text,
            "element_name": gap.get("element_name"),
            "auto_request": gap["severity"] in ("high", "medium"),
        })

    return recommendations


def build_shelf_request_items(
    recommendations: list[dict[str, Any]],
    engagement_id: str,
) -> list[dict[str, Any]]:
    """Build shelf data request items from recommendations.

    Args:
        recommendations: Recommendations that should be auto-requested.
        engagement_id: Engagement to create requests for.

    Returns:
        List of shelf data request item dicts.
    """
    items: list[dict[str, Any]] = []
    for rec in recommendations:
        if not rec.get("auto_request"):
            continue

        category = "documents"
        if "structured_data" in rec.get("gap_type", ""):
            category = "structured_data"
        elif "bpm" in str(rec.get("element_name", "")):
            category = "bpm_process_models"

        priority = "high" if rec["severity"] == "high" else "medium"

        items.append({
            "engagement_id": engagement_id,
            "category": category,
            "item_name": rec["recommendation"],
            "description": f"Auto-generated from gap analysis: {rec.get('gap_type', '')}",
            "priority": priority,
        })

    return items
