"""Client intake service for token-based evidence submission.

Handles intake token generation, validation, file upload processing,
and auto-matching of uploaded files to shelf data request items.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.core.models.engagement import (
    ShelfDataRequestToken,
    UploadFileStatus,
)

logger = logging.getLogger(__name__)

# Default token expiry: 14 days
DEFAULT_TOKEN_EXPIRY_DAYS: int = 14

# Auto-matching threshold: normalized Levenshtein similarity (0.0 to 1.0)
DEFAULT_MATCH_THRESHOLD: float = 0.8


def generate_intake_token(
    request_id: uuid.UUID,
    created_by: str | None = None,
    expiry_days: int = DEFAULT_TOKEN_EXPIRY_DAYS,
) -> ShelfDataRequestToken:
    """Create a new intake token for a shelf data request.

    Args:
        request_id: ID of the shelf data request.
        created_by: Username of the analyst generating the link.
        expiry_days: Number of days until the token expires.

    Returns:
        A new ShelfDataRequestToken (not yet committed to DB).
    """
    expires_at = datetime.now(UTC) + timedelta(days=expiry_days)

    token = ShelfDataRequestToken(
        token=uuid.uuid4(),
        request_id=request_id,
        expires_at=expires_at,
        created_by=created_by,
        used_count=0,
    )

    logger.info(
        "Generated intake token for request %s, expires %s",
        request_id,
        expires_at.isoformat(),
    )

    return token


def validate_intake_token(token_record: ShelfDataRequestToken | None) -> str | None:
    """Validate an intake token. Returns error message or None if valid.

    Args:
        token_record: The token record from the database, or None if not found.

    Returns:
        Error message string if invalid, None if valid.
    """
    if token_record is None:
        return "Invalid intake token."

    if token_record.is_expired:
        return "This upload link has expired. Please contact your engagement manager."

    return None


def normalize_filename(filename: str) -> str:
    """Normalize a filename for matching against request item names.

    Strips extension, replaces separators with spaces, lowercases.

    Args:
        filename: Original filename.

    Returns:
        Normalized name suitable for comparison.
    """
    # Strip path components
    name = Path(filename).stem
    # Replace common separators with spaces
    name = re.sub(r"[_\-.]", " ", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip().lower()
    return name


def compute_name_similarity(name_a: str, name_b: str) -> float:
    """Compute normalized Levenshtein similarity between two strings.

    Uses a simple dynamic programming edit distance. Returns a value
    between 0.0 (completely different) and 1.0 (identical).

    Args:
        name_a: First name (normalized).
        name_b: Second name (normalized).

    Returns:
        Similarity score from 0.0 to 1.0.
    """
    if name_a == name_b:
        return 1.0

    len_a = len(name_a)
    len_b = len(name_b)
    max_len = max(len_a, len_b)

    if max_len == 0:
        return 1.0

    # Compute Levenshtein distance
    if len_a < len_b:
        name_a, name_b = name_b, name_a
        len_a, len_b = len_b, len_a

    # Use single row for space efficiency
    prev_row = list(range(len_b + 1))

    for i in range(1, len_a + 1):
        curr_row = [i] + [0] * len_b
        for j in range(1, len_b + 1):
            cost = 0 if name_a[i - 1] == name_b[j - 1] else 1
            curr_row[j] = min(
                curr_row[j - 1] + 1,  # insertion
                prev_row[j] + 1,  # deletion
                prev_row[j - 1] + cost,  # substitution
            )
        prev_row = curr_row

    distance = prev_row[len_b]
    return 1.0 - (distance / max_len)


def match_filename_to_items(
    filename: str,
    item_names: list[tuple[str, str]],
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> tuple[str | None, float]:
    """Auto-match an uploaded filename to a request item.

    Args:
        filename: The uploaded filename.
        item_names: List of (item_id, item_name) tuples.
        threshold: Minimum similarity for a match.

    Returns:
        Tuple of (matched_item_id, similarity_score) or (None, 0.0).
    """
    normalized_file = normalize_filename(filename)

    best_match_id: str | None = None
    best_score: float = 0.0

    for item_id, item_name in item_names:
        normalized_item = item_name.strip().lower()
        score = compute_name_similarity(normalized_file, normalized_item)

        if score > best_score:
            best_score = score
            best_match_id = item_id

    if best_score >= threshold:
        logger.info(
            "Auto-matched '%s' to item '%s' (score=%.3f)",
            filename,
            best_match_id,
            best_score,
        )
        return best_match_id, best_score

    logger.info(
        "No match for '%s' (best score=%.3f, threshold=%.3f)",
        filename,
        best_score,
        threshold,
    )
    return None, best_score


def build_progress_entry(
    filename: str,
    file_status: UploadFileStatus = UploadFileStatus.QUEUED,
    matched_item_id: str | None = None,
    error: str | None = None,
) -> dict[str, str | None]:
    """Build a progress tracking entry for a single file.

    Args:
        filename: Original filename.
        file_status: Current processing status.
        matched_item_id: ID of matched request item, if any.
        error: Error message if processing failed.

    Returns:
        Dict with file progress information.
    """
    return {
        "filename": filename,
        "status": file_status.value,
        "matched_item_id": matched_item_id,
        "error": error,
    }
