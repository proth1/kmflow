"""Sequence pattern mining from classified action sequences.

Extracts frequent action category n-grams from session sequences
to discover common process patterns and feed variant detection.

Story #235 — Part of Epic #231 (ML Task Segmentation).
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ActionPattern:
    """A frequent action sequence pattern."""

    pattern: tuple[str, ...]
    support: int  # how many sessions contain this pattern
    frequency: float  # support / total_sessions


@dataclass
class SequenceMiningResult:
    """Result of sequence mining across multiple sessions."""

    patterns: list[ActionPattern] = field(default_factory=list)
    sessions_analyzed: int = 0
    total_patterns_found: int = 0


def mine_sequences(
    session_sequences: list[list[str]],
    min_n: int = 2,
    max_n: int = 5,
    min_support: int = 2,
) -> SequenceMiningResult:
    """Extract frequent action category n-grams from session sequences.

    Args:
        session_sequences: List of sessions, each a list of action category
            strings (e.g., ["data_entry", "navigation", "file_operation"]).
        min_n: Minimum n-gram length (default 2).
        max_n: Maximum n-gram length (default 5).
        min_support: Minimum number of sessions a pattern must appear in
            to be included (default 2).

    Returns:
        SequenceMiningResult with patterns sorted by frequency descending.
    """
    if not session_sequences:
        return SequenceMiningResult()

    total_sessions = len(session_sequences)
    pattern_counts: Counter[tuple[str, ...]] = Counter()

    for sequence in session_sequences:
        if len(sequence) < min_n:
            continue

        # Extract unique n-grams per session (count each pattern once per session)
        session_patterns: set[tuple[str, ...]] = set()
        for n in range(min_n, min(max_n + 1, len(sequence) + 1)):
            for i in range(len(sequence) - n + 1):
                ngram = tuple(sequence[i:i + n])
                session_patterns.add(ngram)

        for pattern in session_patterns:
            pattern_counts[pattern] += 1

    # Filter by min_support and build results
    patterns = []
    for pattern, support in pattern_counts.items():
        if support >= min_support:
            patterns.append(ActionPattern(
                pattern=pattern,
                support=support,
                frequency=round(support / total_sessions, 4),
            ))

    # Sort by support descending, then by pattern length descending
    patterns.sort(key=lambda p: (-p.support, -len(p.pattern)))

    result = SequenceMiningResult(
        patterns=patterns,
        sessions_analyzed=total_sessions,
        total_patterns_found=len(patterns),
    )
    logger.info(
        "Sequence mining: %d sessions, %d patterns found (min_support=%d)",
        total_sessions, len(patterns), min_support,
    )
    return result
