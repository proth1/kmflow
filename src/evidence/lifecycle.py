"""Evidence lifecycle state machine and transition management.

Enforces valid state transitions for evidence items:
  PENDING → VALIDATED → ACTIVE → EXPIRED → ARCHIVED
  VALIDATED → ARCHIVED (skip active)

Every transition is logged to an audit trail.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from src.core.models.evidence import ValidationStatus

# Valid state transitions: from_status → set of allowed to_statuses
ALLOWED_TRANSITIONS: dict[ValidationStatus, set[ValidationStatus]] = {
    ValidationStatus.PENDING: {ValidationStatus.VALIDATED},
    ValidationStatus.VALIDATED: {ValidationStatus.ACTIVE, ValidationStatus.ARCHIVED},
    ValidationStatus.ACTIVE: {ValidationStatus.EXPIRED},
    ValidationStatus.EXPIRED: {ValidationStatus.ARCHIVED},
    ValidationStatus.ARCHIVED: set(),  # Terminal state
}


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_status: ValidationStatus, to_status: ValidationStatus) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Invalid transition: {from_status.value} → {to_status.value}")


def validate_transition(from_status: ValidationStatus, to_status: ValidationStatus) -> bool:
    """Check whether a state transition is valid.

    Args:
        from_status: Current status.
        to_status: Desired status.

    Returns:
        True if the transition is valid.

    Raises:
        InvalidTransitionError: If the transition is not allowed.
    """
    allowed = ALLOWED_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidTransitionError(from_status, to_status)
    return True


def compute_content_hash(data: bytes) -> str:
    """Compute SHA-256 hash of raw content bytes.

    The hash is computed on the raw bytes before any transformation
    or normalization, ensuring exact duplicate detection.

    Args:
        data: Raw file content bytes.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    return hashlib.sha256(data).hexdigest()


def build_audit_entry(
    evidence_id: uuid.UUID,
    from_status: ValidationStatus,
    to_status: ValidationStatus,
    actor_id: str | None = None,
    reason: str | None = None,
    pov_run_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Build an audit log entry dict for a state transition.

    Args:
        evidence_id: ID of the evidence item.
        from_status: Previous status.
        to_status: New status.
        actor_id: ID of the user or system performing the transition.
        reason: Human-readable reason for the transition.
        pov_run_id: Optional POV run ID that triggered the transition.

    Returns:
        Dictionary suitable for creating an audit log record.
    """
    return {
        "evidence_id": evidence_id,
        "from_status": from_status.value,
        "to_status": to_status.value,
        "actor_id": actor_id,
        "reason": reason,
        "pov_run_id": str(pov_run_id) if pov_run_id else None,
        "timestamp": datetime.now(tz=UTC).isoformat(),
    }


def classify_by_extension(file_name: str) -> tuple[str | None, float]:
    """Auto-classify evidence category based on file extension.

    Returns the predicted category and a confidence score.
    Items with confidence < 0.6 should be flagged for human review.

    Args:
        file_name: Filename with extension.

    Returns:
        Tuple of (category_string, confidence) or (None, 0.0).
    """
    from pathlib import Path

    from src.evidence.parsers.factory import EXTENSION_TO_CATEGORY

    ext = Path(file_name).suffix.lower()
    category = EXTENSION_TO_CATEGORY.get(ext)

    if category is None:
        return None, 0.0

    # Extension-based classification has high confidence for known types
    return category, 0.85


def check_retention_expired(
    retention_expires_at: datetime | None,
    reference_time: datetime | None = None,
) -> bool:
    """Check if evidence has exceeded its retention period.

    Args:
        retention_expires_at: When the retention period ends.
        reference_time: Current time (defaults to now).

    Returns:
        True if evidence is past its retention date.
    """
    if retention_expires_at is None:
        return False

    if reference_time is None:
        reference_time = datetime.now(tz=UTC)

    return reference_time > retention_expires_at
