"""Industry benchmarking and best practice matching (Story #363).

Computes percentile rankings against industry benchmark distributions
and matches gap findings to relevant best practices.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PercentileRanking:
    """Client percentile ranking against industry benchmark."""

    metric_name: str
    client_value: float
    percentile: float
    percentile_label: str
    distribution: dict[str, float] = field(default_factory=dict)


def compute_percentile(
    client_value: float,
    p25: float,
    p50: float,
    p75: float,
    p90: float,
) -> float:
    """Compute the client's approximate percentile ranking.

    Uses linear interpolation between benchmark percentile points.
    Lower values are assumed to be better (e.g., processing time).

    Args:
        client_value: Client's metric value.
        p25: 25th percentile benchmark.
        p50: 50th percentile benchmark.
        p75: 75th percentile benchmark.
        p90: 90th percentile benchmark.

    Returns:
        Approximate percentile (0-100). Lower means better performance.
    """
    if client_value <= p25:
        # Better than top quartile
        return max(0.0, (client_value / p25) * 25) if p25 > 0 else 0.0
    if client_value <= p50:
        # Between p25 and p50
        return 25 + ((client_value - p25) / (p50 - p25)) * 25 if p50 > p25 else 25.0
    if client_value <= p75:
        # Between p50 and p75
        return 50 + ((client_value - p50) / (p75 - p50)) * 25 if p75 > p50 else 50.0
    if client_value <= p90:
        # Between p75 and p90
        return 75 + ((client_value - p75) / (p90 - p75)) * 15 if p90 > p75 else 75.0
    # Worse than p90
    return min(100.0, 90 + ((client_value - p90) / p90) * 10 if p90 > 0 else 100.0)


def percentile_label(percentile: float) -> str:
    """Return a human-readable label for a percentile ranking.

    Args:
        percentile: Percentile value (0-100).

    Returns:
        Label like "Top Quartile", "Below p50", etc.
    """
    if percentile <= 25:
        return "Top Quartile (p25)"
    if percentile <= 50:
        return "Between p25 and p50"
    if percentile <= 75:
        return "Between p50 and p75"
    if percentile <= 90:
        return "Between p75 and p90"
    return "Below p90"


def rank_client(
    metric_name: str,
    client_value: float,
    p25: float,
    p50: float,
    p75: float,
    p90: float,
) -> PercentileRanking:
    """Compute client percentile ranking with full distribution context.

    Args:
        metric_name: Name of the metric being benchmarked.
        client_value: Client's metric value.
        p25: 25th percentile benchmark.
        p50: 50th percentile benchmark.
        p75: 75th percentile benchmark.
        p90: 90th percentile benchmark.

    Returns:
        PercentileRanking with computed percentile and distribution.
    """
    pct = compute_percentile(client_value, p25, p50, p75, p90)
    return PercentileRanking(
        metric_name=metric_name,
        client_value=client_value,
        percentile=round(pct, 1),
        percentile_label=percentile_label(pct),
        distribution={"p25": p25, "p50": p50, "p75": p75, "p90": p90},
    )


@dataclass
class PracticeMatch:
    """A best practice matched to a gap finding."""

    practice_id: str
    practice_title: str
    practice_domain: str
    practice_industry: str
    gap_id: str
    relevance_score: float
    match_reason: str


def match_gaps_to_practices(
    gaps: list[dict[str, str]],
    practices: list[dict[str, str]],
) -> list[PracticeMatch]:
    """Match gap findings to relevant best practices.

    Matching strategy:
    1. Domain match (exact or substring)
    2. TOM dimension match (if applicable)
    3. Keyword overlap between gap description and practice description

    Args:
        gaps: List of gap dicts with keys: id, description, domain, tom_dimension.
        practices: List of practice dicts with keys: id, title, domain, industry,
            description, tom_dimension.

    Returns:
        List of PracticeMatch sorted by relevance_score descending.
    """
    matches: list[PracticeMatch] = []

    for gap in gaps:
        gap_domain = str(gap.get("domain", "")).lower()
        gap_dimension = str(gap.get("tom_dimension", "")).lower()
        gap_desc = str(gap.get("description", "")).lower()
        gap_words = set(gap_desc.split())

        for practice in practices:
            practice_domain = str(practice.get("domain", "")).lower()
            practice_dimension = str(practice.get("tom_dimension", "")).lower()
            practice_desc = str(practice.get("description", "")).lower()
            practice_words = set(practice_desc.split())

            score = 0.0
            reasons: list[str] = []

            # Domain match
            if gap_domain and practice_domain:
                if gap_domain == practice_domain:
                    score += 0.4
                    reasons.append("domain match")
                elif gap_domain in practice_domain or practice_domain in gap_domain:
                    score += 0.2
                    reasons.append("partial domain match")

            # Dimension match
            if gap_dimension and practice_dimension and gap_dimension == practice_dimension:
                score += 0.3
                reasons.append("dimension match")

            # Keyword overlap
            if gap_words and practice_words:
                overlap = gap_words & practice_words
                # Remove common stop words
                stop_words = {"the", "a", "an", "is", "in", "to", "for", "of", "and", "or", "with", "on", "at"}
                meaningful_overlap = overlap - stop_words
                if meaningful_overlap:
                    overlap_ratio = len(meaningful_overlap) / max(len(gap_words - stop_words), 1)
                    keyword_score = min(overlap_ratio * 0.3, 0.3)
                    score += keyword_score
                    if keyword_score > 0.05:
                        reasons.append("keyword overlap")

            if score > 0.1:
                matches.append(PracticeMatch(
                    practice_id=str(practice.get("id", "")),
                    practice_title=str(practice.get("title", "")),
                    practice_domain=str(practice.get("domain", "")),
                    practice_industry=str(practice.get("industry", "")),
                    gap_id=str(gap.get("id", "")),
                    relevance_score=round(score, 3),
                    match_reason=", ".join(reasons),
                ))

    # Sort by relevance descending
    matches.sort(key=lambda m: m.relevance_score, reverse=True)
    return matches
