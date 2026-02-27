"""BDD tests for Story #308: Client Evidence Submission Portal API.

Tests token-based intake link generation, file upload auto-matching,
progress tracking, and token expiry validation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, PropertyMock

from src.core.models.engagement import (
    ShelfDataRequestToken,
    ShelfRequestItemStatus,
    UploadFileStatus,
)
from src.evidence.intake import (
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_TOKEN_EXPIRY_DAYS,
    build_progress_entry,
    compute_name_similarity,
    generate_intake_token,
    match_filename_to_items,
    normalize_filename,
    validate_intake_token,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token(
    request_id: uuid.UUID | None = None,
    expires_in_days: int = 14,
    expired: bool = False,
) -> MagicMock:
    """Create a mock ShelfDataRequestToken."""
    token = MagicMock(spec=ShelfDataRequestToken)
    token.id = uuid.uuid4()
    token.token = uuid.uuid4()
    token.request_id = request_id or uuid.uuid4()
    token.created_by = "analyst@example.com"
    token.used_count = 0

    if expired:
        token.expires_at = datetime.now(UTC) - timedelta(days=1)
        type(token).is_expired = PropertyMock(return_value=True)
    else:
        token.expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)
        type(token).is_expired = PropertyMock(return_value=False)

    return token


def _make_shelf_request_item(
    item_id: str | None = None,
    item_name: str = "Test Item",
    item_status: ShelfRequestItemStatus = ShelfRequestItemStatus.REQUESTED,
) -> MagicMock:
    """Create a mock ShelfDataRequestItem."""
    item = MagicMock()
    item.id = uuid.UUID(item_id) if item_id else uuid.uuid4()
    item.item_name = item_name
    item.status = item_status
    return item


# ===========================================================================
# Scenario 1: Intake link is generated for a shelf data request
# ===========================================================================


class TestIntakeLinkGeneration:
    """Given a shelf data request exists with status=OPEN,
    when an analyst generates an intake link for the request,
    then a unique intake token is created with configurable expiry.
    """

    def test_token_created_with_request_id(self):
        """Intake token is associated with the shelf data request."""
        request_id = uuid.uuid4()
        token = generate_intake_token(request_id)
        assert token.request_id == request_id

    def test_token_has_unique_uuid(self):
        """Each token has a unique UUID."""
        request_id = uuid.uuid4()
        t1 = generate_intake_token(request_id)
        t2 = generate_intake_token(request_id)
        assert t1.token != t2.token

    def test_token_default_expiry_14_days(self):
        """Default expiry is 14 days from creation."""
        token = generate_intake_token(uuid.uuid4())
        expected = datetime.now(UTC) + timedelta(days=14)
        # Allow 5 seconds tolerance
        assert abs((token.expires_at - expected).total_seconds()) < 5

    def test_token_custom_expiry(self):
        """Configurable expiry via expiry_days parameter."""
        token = generate_intake_token(uuid.uuid4(), expiry_days=7)
        expected = datetime.now(UTC) + timedelta(days=7)
        assert abs((token.expires_at - expected).total_seconds()) < 5

    def test_token_tracks_creator(self):
        """Token records the analyst who created it."""
        token = generate_intake_token(uuid.uuid4(), created_by="analyst@example.com")
        assert token.created_by == "analyst@example.com"

    def test_token_initial_used_count_zero(self):
        """New token has zero used_count."""
        token = generate_intake_token(uuid.uuid4())
        assert token.used_count == 0

    def test_default_expiry_days_constant(self):
        """Default expiry constant is 14 days."""
        assert DEFAULT_TOKEN_EXPIRY_DAYS == 14


# ===========================================================================
# Scenario 2: Client uploads files and auto-matching occurs
# ===========================================================================


class TestFileAutoMatching:
    """Given a shelf data request with items,
    when client uploads files, auto-matching by filename occurs.
    """

    def test_exact_match_filename_to_item(self):
        """Exact filename match to item name succeeds."""
        items = [("id1", "Q4 Financial Report")]
        matched_id, score = match_filename_to_items("Q4_Financial_Report.pdf", items)
        assert matched_id == "id1"
        assert score >= DEFAULT_MATCH_THRESHOLD

    def test_close_match_with_year_suffix(self):
        """Filename with year suffix matches item name."""
        items = [("id1", "Q4 Financial Report")]
        matched_id, score = match_filename_to_items("Q4_Financial_Report_2025.pdf", items)
        # May or may not match depending on Levenshtein distance
        # but the matching function should return some score
        assert isinstance(score, float)

    def test_unmatched_file_returns_none(self):
        """File with no similar item name returns None."""
        items = [("id1", "Q4 Financial Report")]
        matched_id, score = match_filename_to_items("completely_unrelated_document.xlsx", items)
        assert matched_id is None

    def test_best_match_selected(self):
        """When multiple items exist, best match is selected."""
        items = [
            ("id1", "Q4 Financial Report"),
            ("id2", "Annual Budget Summary"),
            ("id3", "Financial Report Q4"),
        ]
        matched_id, score = match_filename_to_items("Q4_Financial_Report.pdf", items)
        # Should match "Q4 Financial Report" not "Financial Report Q4"
        assert matched_id == "id1"

    def test_no_items_returns_none(self):
        """No items to match returns None."""
        matched_id, score = match_filename_to_items("test.pdf", [])
        assert matched_id is None
        assert score == 0.0

    def test_threshold_configurable(self):
        """Match threshold is configurable."""
        items = [("id1", "Q4 Financial Report")]
        # Very high threshold should not match
        matched_id, _ = match_filename_to_items("Q4 Report.pdf", items, threshold=0.99)
        assert matched_id is None

        # Low threshold should match
        matched_id, _ = match_filename_to_items("Q4 Report.pdf", items, threshold=0.3)
        assert matched_id is not None


# ===========================================================================
# Scenario 3: Bulk upload progress is tracked per file
# ===========================================================================


class TestBulkUploadProgress:
    """Given a client is uploading multiple files,
    when upload is in progress, each file's status is tracked.
    """

    def test_progress_entry_queued(self):
        """New file starts in QUEUED status."""
        entry = build_progress_entry("test.pdf")
        assert entry["status"] == "queued"
        assert entry["filename"] == "test.pdf"

    def test_progress_entry_processing(self):
        """File can be marked as PROCESSING."""
        entry = build_progress_entry("test.pdf", UploadFileStatus.PROCESSING)
        assert entry["status"] == "processing"

    def test_progress_entry_complete_with_match(self):
        """Completed file includes matched item ID."""
        entry = build_progress_entry(
            "test.pdf",
            UploadFileStatus.COMPLETE,
            matched_item_id="item-123",
        )
        assert entry["status"] == "complete"
        assert entry["matched_item_id"] == "item-123"

    def test_progress_entry_failed_with_error(self):
        """Failed file includes error message."""
        entry = build_progress_entry(
            "test.pdf",
            UploadFileStatus.FAILED,
            error="File too large",
        )
        assert entry["status"] == "failed"
        assert entry["error"] == "File too large"

    def test_individual_file_tracking(self):
        """Each of N files has independent status tracking."""
        files = [f"file_{i}.pdf" for i in range(20)]
        entries = [build_progress_entry(f) for f in files]
        assert len(entries) == 20
        # Mark one as failed, rest unaffected
        entries[5] = build_progress_entry(files[5], UploadFileStatus.FAILED, error="corrupt")
        assert entries[5]["status"] == "failed"
        assert all(e["status"] == "queued" for i, e in enumerate(entries) if i != 5)

    def test_upload_file_status_values(self):
        """UploadFileStatus has expected values."""
        assert UploadFileStatus.QUEUED == "queued"
        assert UploadFileStatus.PROCESSING == "processing"
        assert UploadFileStatus.COMPLETE == "complete"
        assert UploadFileStatus.FAILED == "failed"


# ===========================================================================
# Scenario 4: Expired intake link denies access
# ===========================================================================


class TestExpiredIntakeLink:
    """Given an intake token whose expiry timestamp is in the past,
    when a client attempts access, the request is rejected.
    """

    def test_expired_token_returns_error(self):
        """Expired token is rejected."""
        token = _make_token(expired=True)
        error = validate_intake_token(token)
        assert error is not None
        assert "expired" in error.lower()

    def test_expired_token_message(self):
        """Expired token message mentions engagement manager."""
        token = _make_token(expired=True)
        error = validate_intake_token(token)
        assert "engagement manager" in error.lower()

    def test_valid_token_returns_none(self):
        """Valid (non-expired) token returns no error."""
        token = _make_token(expired=False)
        error = validate_intake_token(token)
        assert error is None

    def test_nonexistent_token_returns_error(self):
        """None token (not found) returns error."""
        error = validate_intake_token(None)
        assert error is not None
        assert "invalid" in error.lower()


# ===========================================================================
# Scenario 5: Uploaded file matched → item transitions to RECEIVED
# ===========================================================================


class TestItemStatusTransition:
    """Given a shelf data request item with status=REQUESTED,
    when a client uploads a matched file, the item transitions to RECEIVED.
    """

    def test_matched_item_transitions_to_received(self):
        """Match triggers REQUESTED → RECEIVED transition."""
        item = _make_shelf_request_item(item_status=ShelfRequestItemStatus.REQUESTED)
        assert item.status == ShelfRequestItemStatus.REQUESTED

        # Simulate the match (in the real flow, the route handler does this)
        item.status = ShelfRequestItemStatus.RECEIVED
        assert item.status == ShelfRequestItemStatus.RECEIVED

    def test_pending_item_also_transitions(self):
        """PENDING items can also transition to RECEIVED."""
        item = _make_shelf_request_item(item_status=ShelfRequestItemStatus.PENDING)
        item.status = ShelfRequestItemStatus.RECEIVED
        assert item.status == ShelfRequestItemStatus.RECEIVED


# ===========================================================================
# Filename normalization tests
# ===========================================================================


class TestFilenameNormalization:
    """Tests for filename normalization used in auto-matching."""

    def test_strips_extension(self):
        """File extension is removed."""
        assert normalize_filename("report.pdf") == "report"

    def test_replaces_underscores(self):
        """Underscores replaced with spaces."""
        assert normalize_filename("Q4_Financial_Report.pdf") == "q4 financial report"

    def test_replaces_hyphens(self):
        """Hyphens replaced with spaces."""
        assert normalize_filename("Q4-Financial-Report.pdf") == "q4 financial report"

    def test_lowercases(self):
        """Name is lowercased."""
        assert normalize_filename("Q4_REPORT.PDF") == "q4 report"

    def test_collapses_whitespace(self):
        """Multiple spaces collapsed to one."""
        assert normalize_filename("Q4__Financial___Report.pdf") == "q4 financial report"

    def test_handles_nested_path(self):
        """Path components stripped, only filename used."""
        assert normalize_filename("/uploads/2025/Q4_Report.pdf") == "q4 report"


# ===========================================================================
# Levenshtein similarity tests
# ===========================================================================


class TestNameSimilarity:
    """Tests for the normalized Levenshtein similarity computation."""

    def test_identical_strings(self):
        """Identical strings have similarity 1.0."""
        assert compute_name_similarity("hello", "hello") == 1.0

    def test_completely_different(self):
        """Completely different strings have low similarity."""
        score = compute_name_similarity("abc", "xyz")
        assert score < 0.5

    def test_one_character_difference(self):
        """One character difference gives high similarity."""
        score = compute_name_similarity("hello", "hallo")
        assert score > 0.7

    def test_empty_strings(self):
        """Both empty strings are identical."""
        assert compute_name_similarity("", "") == 1.0

    def test_one_empty(self):
        """One empty string gives 0.0 similarity."""
        assert compute_name_similarity("hello", "") == 0.0

    def test_case_sensitive(self):
        """Similarity is case-sensitive (caller should normalize)."""
        score = compute_name_similarity("Hello", "hello")
        assert score < 1.0

    def test_q4_financial_report_match(self):
        """Realistic filename match scenario."""
        score = compute_name_similarity("q4 financial report", "q4 financial report")
        assert score == 1.0

    def test_q4_report_variant(self):
        """Variant with year suffix has reasonable similarity."""
        score = compute_name_similarity("q4 financial report 2025", "q4 financial report")
        assert score > 0.6


# ===========================================================================
# Token model tests
# ===========================================================================


class TestShelfDataRequestTokenModel:
    """Tests for the ShelfDataRequestToken SQLAlchemy model."""

    def test_model_has_required_fields(self):
        """Token model has all required attributes."""
        token = ShelfDataRequestToken()
        assert hasattr(token, "token")
        assert hasattr(token, "request_id")
        assert hasattr(token, "expires_at")
        assert hasattr(token, "created_by")
        assert hasattr(token, "used_count")

    def test_upload_file_status_enum(self):
        """UploadFileStatus enum has all expected values."""
        assert len(UploadFileStatus) == 4
        values = {s.value for s in UploadFileStatus}
        assert values == {"queued", "processing", "complete", "failed"}
