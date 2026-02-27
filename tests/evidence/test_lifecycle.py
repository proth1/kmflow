"""Tests for Evidence Lifecycle State Machine — Story #301.

Covers all 6 BDD scenarios:
1. Uploaded evidence is hashed on ingest
2. Auto-classification assigns a taxonomy category
3. Analyst approval transitions evidence to VALIDATED
4. Evidence is activated for POV generation
5. Evidence with expired retention period transitions to EXPIRED
6. Duplicate evidence is detected and flagged
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.core.models.evidence import ValidationStatus
from src.evidence.lifecycle import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    build_audit_entry,
    check_retention_expired,
    classify_by_extension,
    compute_content_hash,
    validate_transition,
)

# ---------------------------------------------------------------------------
# BDD Scenario 1: Uploaded evidence is hashed on ingest
# ---------------------------------------------------------------------------


class TestBDDScenario1HashOnIngest:
    """Given a new evidence file is uploaded to the ingestion endpoint
    When the ingest processor handles the file
    Then the evidence record is created with status=PENDING
      And a SHA-256 content hash is computed and stored on the record
      And the hash is computed before any transformation or normalization
    """

    def test_sha256_hash_of_known_bytes(self) -> None:
        """SHA-256 of known input matches expected digest."""
        data = b"hello world"
        expected = hashlib.sha256(data).hexdigest()
        assert compute_content_hash(data) == expected

    def test_hash_is_hex_string(self) -> None:
        """Hash output is a hex-encoded string."""
        result = compute_content_hash(b"test")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest is 64 chars
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_bytes_produces_hash(self) -> None:
        """Empty bytes still produce a valid SHA-256 hash."""
        result = compute_content_hash(b"")
        assert len(result) == 64
        assert result == hashlib.sha256(b"").hexdigest()

    def test_different_content_produces_different_hash(self) -> None:
        """Different content produces different hashes."""
        hash1 = compute_content_hash(b"file content A")
        hash2 = compute_content_hash(b"file content B")
        assert hash1 != hash2

    def test_same_content_produces_same_hash(self) -> None:
        """Identical content produces identical hashes (deterministic)."""
        data = b"identical content"
        assert compute_content_hash(data) == compute_content_hash(data)

    def test_binary_content_hashed(self) -> None:
        """Binary (non-text) content is hashed correctly."""
        binary_data = bytes(range(256))
        result = compute_content_hash(binary_data)
        assert result == hashlib.sha256(binary_data).hexdigest()

    def test_pending_is_initial_state(self) -> None:
        """PENDING is a valid from-state in the transition map."""
        assert ValidationStatus.PENDING in ALLOWED_TRANSITIONS


# ---------------------------------------------------------------------------
# BDD Scenario 2: Auto-classification assigns a taxonomy category
# ---------------------------------------------------------------------------


class TestBDDScenario2AutoClassification:
    """Given an evidence item with status=PENDING
    When the auto-classification job runs on the item
    Then the evidence is assigned exactly one category from the 12-type taxonomy
      And the assigned category and confidence score are stored on the record
      And items with confidence < 0.6 are flagged for mandatory human review
    """

    def test_pdf_classified_as_documents(self) -> None:
        """PDF file classified as 'documents'."""
        category, confidence = classify_by_extension("report.pdf")
        assert category == "documents"
        assert confidence >= 0.6

    def test_xlsx_classified_as_structured_data(self) -> None:
        """Excel file classified as 'structured_data'."""
        category, confidence = classify_by_extension("data.xlsx")
        assert category == "structured_data"
        assert confidence >= 0.6

    def test_bpmn_classified_as_bpm(self) -> None:
        """BPMN file classified as 'bpm_process_models'."""
        category, confidence = classify_by_extension("process.bpmn")
        assert category == "bpm_process_models"
        assert confidence >= 0.6

    def test_csv_classified_as_structured_data(self) -> None:
        """CSV file classified as 'structured_data'."""
        category, confidence = classify_by_extension("data.csv")
        assert category == "structured_data"
        assert confidence >= 0.6

    def test_json_classified_as_structured_data(self) -> None:
        """JSON file classified as 'structured_data'."""
        category, confidence = classify_by_extension("config.json")
        assert category == "structured_data"
        assert confidence >= 0.6

    def test_unknown_extension_returns_none(self) -> None:
        """Unknown extension returns (None, 0.0)."""
        category, confidence = classify_by_extension("file.xyz")
        assert category is None
        assert confidence == 0.0

    def test_unknown_confidence_below_threshold(self) -> None:
        """Unknown extension has confidence < 0.6 (flagged for human review)."""
        _, confidence = classify_by_extension("mystery.zzz")
        assert confidence < 0.6

    def test_known_extension_confidence_above_threshold(self) -> None:
        """Known extension has confidence >= 0.6 (no human review needed)."""
        _, confidence = classify_by_extension("report.pdf")
        assert confidence >= 0.6

    def test_case_insensitive_extension(self) -> None:
        """Extension matching is case-insensitive."""
        category, _ = classify_by_extension("REPORT.PDF")
        assert category == "documents"

    def test_returns_exactly_one_category(self) -> None:
        """Each file gets exactly one category (not a list)."""
        category, _ = classify_by_extension("file.pdf")
        assert isinstance(category, str)

    def test_confidence_is_float(self) -> None:
        """Confidence score is a float."""
        _, confidence = classify_by_extension("report.pdf")
        assert isinstance(confidence, float)


# ---------------------------------------------------------------------------
# BDD Scenario 3: Analyst approval transitions evidence to VALIDATED
# ---------------------------------------------------------------------------


class TestBDDScenario3AnalystApproval:
    """Given an evidence item with status=PENDING that has been auto-classified
    When an analyst reviews and approves the evidence via the review endpoint
    Then the evidence status transitions to VALIDATED
      And an audit log entry is created recording the approver, timestamp, and previous status
      And the evidence becomes eligible for POV generation
    """

    def test_pending_to_validated_allowed(self) -> None:
        """PENDING → VALIDATED is a valid transition."""
        assert validate_transition(ValidationStatus.PENDING, ValidationStatus.VALIDATED)

    def test_pending_to_active_rejected(self) -> None:
        """PENDING → ACTIVE is NOT allowed (must go through VALIDATED)."""
        with pytest.raises(InvalidTransitionError):
            validate_transition(ValidationStatus.PENDING, ValidationStatus.ACTIVE)

    def test_pending_to_expired_rejected(self) -> None:
        """PENDING → EXPIRED is NOT allowed."""
        with pytest.raises(InvalidTransitionError):
            validate_transition(ValidationStatus.PENDING, ValidationStatus.EXPIRED)

    def test_audit_entry_records_approver(self) -> None:
        """Audit entry records actor_id (the approver)."""
        eid = uuid.uuid4()
        entry = build_audit_entry(
            evidence_id=eid,
            from_status=ValidationStatus.PENDING,
            to_status=ValidationStatus.VALIDATED,
            actor_id="analyst-123",
        )
        assert entry["actor_id"] == "analyst-123"

    def test_audit_entry_records_previous_status(self) -> None:
        """Audit entry records from_status."""
        eid = uuid.uuid4()
        entry = build_audit_entry(
            evidence_id=eid,
            from_status=ValidationStatus.PENDING,
            to_status=ValidationStatus.VALIDATED,
        )
        assert entry["from_status"] == "pending"
        assert entry["to_status"] == "validated"

    def test_audit_entry_has_timestamp(self) -> None:
        """Audit entry includes an ISO timestamp."""
        eid = uuid.uuid4()
        entry = build_audit_entry(
            evidence_id=eid,
            from_status=ValidationStatus.PENDING,
            to_status=ValidationStatus.VALIDATED,
        )
        assert "timestamp" in entry
        # Validate it parses as ISO format
        datetime.fromisoformat(entry["timestamp"])

    def test_audit_entry_has_evidence_id(self) -> None:
        """Audit entry includes the evidence_id."""
        eid = uuid.uuid4()
        entry = build_audit_entry(
            evidence_id=eid,
            from_status=ValidationStatus.PENDING,
            to_status=ValidationStatus.VALIDATED,
        )
        assert entry["evidence_id"] == eid

    def test_audit_entry_reason_optional(self) -> None:
        """Reason is optional and defaults to None."""
        eid = uuid.uuid4()
        entry = build_audit_entry(
            evidence_id=eid,
            from_status=ValidationStatus.PENDING,
            to_status=ValidationStatus.VALIDATED,
        )
        assert entry["reason"] is None

    def test_audit_entry_with_reason(self) -> None:
        """Reason can be provided."""
        eid = uuid.uuid4()
        entry = build_audit_entry(
            evidence_id=eid,
            from_status=ValidationStatus.PENDING,
            to_status=ValidationStatus.VALIDATED,
            reason="Analyst verified document authenticity",
        )
        assert entry["reason"] == "Analyst verified document authenticity"


# ---------------------------------------------------------------------------
# BDD Scenario 4: Evidence is activated for POV generation
# ---------------------------------------------------------------------------


class TestBDDScenario4Activation:
    """Given an evidence item with status=VALIDATED
    When the evidence is activated for use in a POV generation run
    Then the status transitions to ACTIVE
      And an audit log entry records the activation timestamp and triggering POV run ID
    """

    def test_validated_to_active_allowed(self) -> None:
        """VALIDATED → ACTIVE is a valid transition."""
        assert validate_transition(ValidationStatus.VALIDATED, ValidationStatus.ACTIVE)

    def test_validated_to_archived_allowed(self) -> None:
        """VALIDATED → ARCHIVED is also valid (skip active path)."""
        assert validate_transition(ValidationStatus.VALIDATED, ValidationStatus.ARCHIVED)

    def test_audit_entry_records_pov_run_id(self) -> None:
        """Audit entry includes the POV run ID that triggered activation."""
        eid = uuid.uuid4()
        pov_id = uuid.uuid4()
        entry = build_audit_entry(
            evidence_id=eid,
            from_status=ValidationStatus.VALIDATED,
            to_status=ValidationStatus.ACTIVE,
            pov_run_id=pov_id,
        )
        assert entry["pov_run_id"] == str(pov_id)

    def test_audit_entry_pov_run_id_optional(self) -> None:
        """POV run ID is optional (manual activation)."""
        eid = uuid.uuid4()
        entry = build_audit_entry(
            evidence_id=eid,
            from_status=ValidationStatus.VALIDATED,
            to_status=ValidationStatus.ACTIVE,
        )
        assert entry["pov_run_id"] is None

    def test_active_to_validated_rejected(self) -> None:
        """ACTIVE → VALIDATED is NOT allowed (no backward transitions)."""
        with pytest.raises(InvalidTransitionError):
            validate_transition(ValidationStatus.ACTIVE, ValidationStatus.VALIDATED)


# ---------------------------------------------------------------------------
# BDD Scenario 5: Expired retention period
# ---------------------------------------------------------------------------


class TestBDDScenario5RetentionExpiry:
    """Given an evidence item with status=ACTIVE
      And the evidence has a configured retention_expires_at timestamp in the past
    When the scheduled retention check job runs
    Then the evidence status transitions to EXPIRED
      And an audit log entry is created with reason=RETENTION_EXPIRED
      And the evidence is no longer returned in active evidence queries
    """

    def test_active_to_expired_allowed(self) -> None:
        """ACTIVE → EXPIRED is a valid transition."""
        assert validate_transition(ValidationStatus.ACTIVE, ValidationStatus.EXPIRED)

    def test_expired_to_archived_allowed(self) -> None:
        """EXPIRED → ARCHIVED is a valid transition."""
        assert validate_transition(ValidationStatus.EXPIRED, ValidationStatus.ARCHIVED)

    def test_past_retention_is_expired(self) -> None:
        """Retention in the past returns True."""
        past = datetime.now(tz=UTC) - timedelta(days=1)
        assert check_retention_expired(past) is True

    def test_future_retention_not_expired(self) -> None:
        """Retention in the future returns False."""
        future = datetime.now(tz=UTC) + timedelta(days=365)
        assert check_retention_expired(future) is False

    def test_none_retention_not_expired(self) -> None:
        """None retention (indefinite) returns False."""
        assert check_retention_expired(None) is False

    def test_reference_time_override(self) -> None:
        """Reference time can be overridden for testing."""
        expires = datetime(2026, 6, 1, tzinfo=UTC)
        before = datetime(2026, 5, 1, tzinfo=UTC)
        after = datetime(2026, 7, 1, tzinfo=UTC)
        assert check_retention_expired(expires, reference_time=before) is False
        assert check_retention_expired(expires, reference_time=after) is True

    def test_audit_entry_with_retention_reason(self) -> None:
        """Audit entry records RETENTION_EXPIRED reason."""
        eid = uuid.uuid4()
        entry = build_audit_entry(
            evidence_id=eid,
            from_status=ValidationStatus.ACTIVE,
            to_status=ValidationStatus.EXPIRED,
            reason="RETENTION_EXPIRED",
        )
        assert entry["reason"] == "RETENTION_EXPIRED"

    def test_expired_to_active_rejected(self) -> None:
        """EXPIRED → ACTIVE is NOT allowed (no reactivation)."""
        with pytest.raises(InvalidTransitionError):
            validate_transition(ValidationStatus.EXPIRED, ValidationStatus.ACTIVE)


# ---------------------------------------------------------------------------
# BDD Scenario 6: Duplicate evidence detection
# ---------------------------------------------------------------------------


class TestBDDScenario6DuplicateDetection:
    """Given an evidence item already exists with content_hash="abc123"
    When a new upload produces the same SHA-256 content hash "abc123"
    Then the new upload is flagged as a DUPLICATE
      And the response includes the ID of the existing evidence item
      And no new evidence record is created (deduplication enforced)
    """

    def test_identical_content_same_hash(self) -> None:
        """Identical file content produces the same hash for dedup matching."""
        content = b"This is the exact same document content"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)
        assert hash1 == hash2

    def test_modified_content_different_hash(self) -> None:
        """Even a single byte change produces a different hash."""
        original = b"Original document content"
        modified = b"Original document contenT"  # Capital T
        assert compute_content_hash(original) != compute_content_hash(modified)

    def test_content_hash_column_exists(self) -> None:
        """EvidenceItem has content_hash column for dedup index."""
        from src.core.models.evidence import EvidenceItem

        columns = {c.name for c in EvidenceItem.__table__.columns}
        assert "content_hash" in columns

    def test_duplicate_of_id_column_exists(self) -> None:
        """EvidenceItem has duplicate_of_id FK for dedup linkage."""
        from src.core.models.evidence import EvidenceItem

        columns = {c.name for c in EvidenceItem.__table__.columns}
        assert "duplicate_of_id" in columns


# ---------------------------------------------------------------------------
# State machine completeness
# ---------------------------------------------------------------------------


class TestStateMachineCompleteness:
    """Verify the state machine covers all valid/invalid transitions."""

    def test_all_validation_statuses_in_transitions(self) -> None:
        """Every ValidationStatus has an entry in ALLOWED_TRANSITIONS."""
        for status in ValidationStatus:
            assert status in ALLOWED_TRANSITIONS, f"{status} missing from ALLOWED_TRANSITIONS"

    def test_archived_is_terminal(self) -> None:
        """ARCHIVED has no outgoing transitions."""
        assert ALLOWED_TRANSITIONS[ValidationStatus.ARCHIVED] == set()

    def test_archived_to_anything_rejected(self) -> None:
        """Cannot transition from ARCHIVED to any state."""
        for status in ValidationStatus:
            if status != ValidationStatus.ARCHIVED:
                with pytest.raises(InvalidTransitionError):
                    validate_transition(ValidationStatus.ARCHIVED, status)

    def test_self_transitions_rejected(self) -> None:
        """Cannot transition to the same state."""
        for status in ValidationStatus:
            with pytest.raises(InvalidTransitionError):
                validate_transition(status, status)

    def test_invalid_transition_error_attributes(self) -> None:
        """InvalidTransitionError stores from/to statuses."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(ValidationStatus.ACTIVE, ValidationStatus.PENDING)
        assert exc_info.value.from_status == ValidationStatus.ACTIVE
        assert exc_info.value.to_status == ValidationStatus.PENDING
        assert "active" in str(exc_info.value).lower()
        assert "pending" in str(exc_info.value).lower()

    def test_validate_transition_returns_true(self) -> None:
        """Valid transition returns True."""
        result = validate_transition(ValidationStatus.PENDING, ValidationStatus.VALIDATED)
        assert result is True

    def test_happy_path_full_lifecycle(self) -> None:
        """Full lifecycle path: PENDING → VALIDATED → ACTIVE → EXPIRED → ARCHIVED."""
        path = [
            (ValidationStatus.PENDING, ValidationStatus.VALIDATED),
            (ValidationStatus.VALIDATED, ValidationStatus.ACTIVE),
            (ValidationStatus.ACTIVE, ValidationStatus.EXPIRED),
            (ValidationStatus.EXPIRED, ValidationStatus.ARCHIVED),
        ]
        for from_s, to_s in path:
            assert validate_transition(from_s, to_s)

    def test_skip_active_path(self) -> None:
        """Alternate path: PENDING → VALIDATED → ARCHIVED (skip ACTIVE)."""
        assert validate_transition(ValidationStatus.PENDING, ValidationStatus.VALIDATED)
        assert validate_transition(ValidationStatus.VALIDATED, ValidationStatus.ARCHIVED)
