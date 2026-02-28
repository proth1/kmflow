"""Tests for ObligationEnforcer service.

Covers all individual obligation methods and the combined enforce_all() entry point.
No database or async dependencies — all methods are pure functions.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.api.services.obligation_enforcer import ObligationEnforcer
from src.core.models.pdp import ObligationType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _obligation(ob_type: ObligationType, params: dict[str, Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(obligation_type=ob_type, parameters=params or {})


# ---------------------------------------------------------------------------
# apply_masking
# ---------------------------------------------------------------------------


def test_apply_masking_masks_specified_fields() -> None:
    """Specified fields are replaced with '***'."""
    data = {"name": "Alice", "ssn": "123-45-6789", "dob": "1990-01-01", "score": 95}
    result = ObligationEnforcer.apply_masking(data, ["ssn", "dob"])
    assert result["ssn"] == "***"
    assert result["dob"] == "***"
    assert result["name"] == "Alice"
    assert result["score"] == 95


def test_apply_masking_no_fields_unchanged() -> None:
    """Empty field list returns data unchanged."""
    data = {"ssn": "123-45-6789"}
    result = ObligationEnforcer.apply_masking(data, [])
    assert result == data


def test_apply_masking_does_not_mutate_original() -> None:
    """Original dict is not modified."""
    data = {"ssn": "123"}
    original_ssn = data["ssn"]
    ObligationEnforcer.apply_masking(data, ["ssn"])
    assert data["ssn"] == original_ssn


def test_apply_masking_nested_dict() -> None:
    """Masking recurses into nested dicts."""
    data = {"person": {"ssn": "123", "name": "Alice"}, "other": "value"}
    result = ObligationEnforcer.apply_masking(data, ["ssn"])
    assert result["person"]["ssn"] == "***"
    assert result["person"]["name"] == "Alice"


def test_apply_masking_list_of_dicts() -> None:
    """Masking recurses into lists of dicts."""
    data = {"items": [{"ssn": "123", "id": 1}, {"ssn": "456", "id": 2}]}
    result = ObligationEnforcer.apply_masking(data, ["ssn"])
    assert result["items"][0]["ssn"] == "***"
    assert result["items"][1]["ssn"] == "***"
    assert result["items"][0]["id"] == 1


def test_apply_masking_nonexistent_field_ignored() -> None:
    """Masking a field that does not exist in data is a no-op."""
    data = {"name": "Bob"}
    result = ObligationEnforcer.apply_masking(data, ["ssn", "dob"])
    assert result == {"name": "Bob"}


# ---------------------------------------------------------------------------
# apply_cohort_suppression
# ---------------------------------------------------------------------------


def test_apply_cohort_suppression_below_threshold_returns_none() -> None:
    """cohort_size below min_cohort returns None (suppression)."""
    data = {"cohort_size": 3, "results": [1, 2, 3]}
    result = ObligationEnforcer.apply_cohort_suppression(data, min_cohort=5)
    assert result is None


def test_apply_cohort_suppression_at_threshold_permits() -> None:
    """cohort_size equal to min_cohort is permitted."""
    data = {"cohort_size": 5, "results": [1, 2, 3, 4, 5]}
    result = ObligationEnforcer.apply_cohort_suppression(data, min_cohort=5)
    assert result is not None
    assert result["cohort_size"] == 5


def test_apply_cohort_suppression_above_threshold_permits() -> None:
    """cohort_size above threshold is permitted."""
    data = {"cohort_size": 20, "results": list(range(20))}
    result = ObligationEnforcer.apply_cohort_suppression(data, min_cohort=5)
    assert result is not None


def test_apply_cohort_suppression_no_cohort_key_permits() -> None:
    """Missing cohort_size key does not trigger suppression."""
    data = {"results": [1, 2, 3]}
    result = ObligationEnforcer.apply_cohort_suppression(data, min_cohort=10)
    assert result is not None
    assert result == {"results": [1, 2, 3]}


# ---------------------------------------------------------------------------
# apply_watermark
# ---------------------------------------------------------------------------


def test_apply_watermark_injects_watermark_block() -> None:
    """Watermark block is added with recipient and issued_at."""
    data = {"id": "ev-001", "name": "Test Evidence"}
    result = ObligationEnforcer.apply_watermark(data, actor="lead@example.com")
    assert "_watermark" in result
    assert result["_watermark"]["recipient"] == "lead@example.com"
    assert "issued_at" in result["_watermark"]


def test_apply_watermark_preserves_existing_fields() -> None:
    """Watermarking does not remove existing fields."""
    data = {"id": "ev-001", "status": "active"}
    result = ObligationEnforcer.apply_watermark(data, actor="user@example.com")
    assert result["id"] == "ev-001"
    assert result["status"] == "active"


def test_apply_watermark_does_not_mutate_original() -> None:
    """Original dict is not modified."""
    data = {"id": "ev-001"}
    ObligationEnforcer.apply_watermark(data, actor="user@example.com")
    assert "_watermark" not in data


# ---------------------------------------------------------------------------
# apply_field_allowlist
# ---------------------------------------------------------------------------


def test_apply_field_allowlist_keeps_allowed_fields() -> None:
    """Only allowed fields remain in the result."""
    data = {"id": "1", "name": "Alice", "ssn": "123", "salary": 100000}
    result = ObligationEnforcer.apply_field_allowlist(data, allowed=["id", "name"])
    assert set(result.keys()) == {"id", "name"}
    assert result["id"] == "1"
    assert result["name"] == "Alice"


def test_apply_field_allowlist_empty_allowed_returns_empty() -> None:
    """Empty allowed list returns empty dict."""
    data = {"id": "1", "name": "Alice"}
    result = ObligationEnforcer.apply_field_allowlist(data, allowed=[])
    assert result == {}


def test_apply_field_allowlist_nonexistent_allowed_fields_ignored() -> None:
    """Allowed fields not present in data are silently skipped."""
    data = {"id": "1"}
    result = ObligationEnforcer.apply_field_allowlist(data, allowed=["id", "nonexistent"])
    assert result == {"id": "1"}


def test_apply_field_allowlist_does_not_mutate_original() -> None:
    """Original dict is not modified."""
    data = {"id": "1", "ssn": "123"}
    ObligationEnforcer.apply_field_allowlist(data, allowed=["id"])
    assert "ssn" in data


# ---------------------------------------------------------------------------
# enforce_all combined
# ---------------------------------------------------------------------------


def test_enforce_all_combined_masking_and_watermark() -> None:
    """enforce_all applies masking then watermark in sequence."""
    data = {"id": "ev-001", "ssn": "123-45-6789", "cohort_size": 20}
    obligations = [
        _obligation(ObligationType.MASK_FIELDS, {"fields": ["ssn"]}),
        _obligation(ObligationType.APPLY_WATERMARK, {}),
    ]
    result = ObligationEnforcer.enforce_all(data, obligations, actor="lead@example.com")
    assert result is not None
    assert result["ssn"] == "***"
    assert "_watermark" in result


def test_enforce_all_suppression_short_circuits() -> None:
    """enforce_all returns None immediately when suppression fires."""
    data = {"cohort_size": 2, "results": [1, 2]}
    obligations = [
        _obligation(ObligationType.SUPPRESS_COHORT, {"min_cohort": 5}),
        _obligation(ObligationType.APPLY_WATERMARK, {}),  # should not run
    ]
    result = ObligationEnforcer.enforce_all(data, obligations, actor="anyone@example.com")
    assert result is None


def test_enforce_all_no_obligations_returns_unchanged() -> None:
    """enforce_all with empty obligations returns data unchanged."""
    data = {"id": "1", "value": 42}
    result = ObligationEnforcer.enforce_all(data, [], actor="user@example.com")
    assert result == data


def test_enforce_all_field_allowlist_after_masking() -> None:
    """enforce_all applies masking first, then strips disallowed fields."""
    data = {"id": "1", "ssn": "123", "salary": 50000, "name": "Alice"}
    obligations = [
        _obligation(ObligationType.MASK_FIELDS, {"fields": ["ssn"]}),
        _obligation(ObligationType.ENFORCE_FIELD_ALLOWLIST, {"allowed_fields": ["id", "name"]}),
    ]
    result = ObligationEnforcer.enforce_all(data, obligations, actor="user@example.com")
    assert result is not None
    # Only id and name after allowlist filter
    assert set(result.keys()) == {"id", "name"}


def test_enforce_all_retention_limit_truncates_lists() -> None:
    """enforce_all applies retention limit to list fields."""
    data = {"items": list(range(100)), "name": "batch"}
    obligations = [
        _obligation(ObligationType.APPLY_RETENTION_LIMIT, {"limit": 10}),
    ]
    result = ObligationEnforcer.enforce_all(data, obligations, actor="user@example.com")
    assert result is not None
    assert len(result["items"]) == 10
    assert result["name"] == "batch"


def test_enforce_all_unknown_obligation_type_logs_and_skips() -> None:
    """Unknown obligation types are logged and skipped without raising."""
    data = {"id": "1"}
    bad_ob = SimpleNamespace(obligation_type="totally_unknown_type", parameters={})
    result = ObligationEnforcer.enforce_all(data, [bad_ob], actor="user@example.com")
    assert result == {"id": "1"}


def test_enforce_all_log_enhanced_audit_no_data_change() -> None:
    """LOG_ENHANCED_AUDIT obligation does not modify response data."""
    data = {"id": "1", "name": "Alice"}
    obligations = [_obligation(ObligationType.LOG_ENHANCED_AUDIT, {})]
    result = ObligationEnforcer.enforce_all(data, obligations, actor="user@example.com")
    assert result == {"id": "1", "name": "Alice"}
