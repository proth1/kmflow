"""BDD tests for single-case timeline replay (Story #337).

Scenarios:
  1. Replay Frame Generation — 10 events → 10 chronological frames
  2. Frame Content Completeness — each frame has all required fields
  3. Paginated Frame Retrieval — limit/offset with pagination metadata
  4. Dark Segment Visual Flagging — confidence < 0.4 → brightness="dark"
"""

from __future__ import annotations

import uuid
from typing import Any

from src.core.services.single_case_replay import (
    SingleCaseReplayResult,
    build_frames_from_events,
    classify_brightness,
    generate_single_case_replay,
    get_paginated_frames,
)

# -- Helpers ------------------------------------------------------------------


def _make_event(
    activity: str = "Submit Application",
    performer: str = "Analyst",
    confidence: float = 0.85,
    brightness: str | None = None,
    evidence_refs: list[str] | None = None,
    timestamp: str = "2026-01-15T10:00:00+00:00",
) -> dict[str, Any]:
    """Create a canonical event dict for testing."""
    return {
        "activity_name": activity,
        "performer_role_ref": performer,
        "confidence_score": confidence,
        "brightness": brightness,
        "evidence_refs": evidence_refs or [],
        "timestamp_utc": timestamp,
    }


def _make_events(count: int) -> list[dict[str, Any]]:
    """Create N sequential canonical events."""
    activities = [
        "Submit Application",
        "Review Documents",
        "Verify Identity",
        "Credit Check",
        "Risk Assessment",
        "Underwriting",
        "Approval Decision",
        "Generate Offer",
        "Client Acceptance",
        "Disbursement",
    ]
    events = []
    for i in range(count):
        activity = activities[i % len(activities)]
        events.append(
            _make_event(
                activity=activity,
                performer=f"Role_{i}",
                confidence=0.5 + (i * 0.05),
                timestamp=f"2026-01-15T{10 + i:02d}:00:00+00:00",
            )
        )
    return events


# -- Scenario 1: Replay Frame Generation -------------------------------------


class TestReplayFrameGeneration:
    """Scenario 1: Given a case with 10 events, 10 frames are generated."""

    def test_10_events_produce_10_frames(self) -> None:
        events = _make_events(10)
        result = generate_single_case_replay("case-001", events)
        assert result.total_frames == 10

    def test_frames_in_chronological_order(self) -> None:
        events = _make_events(5)
        result = generate_single_case_replay("case-001", events)
        timestamps = [f.timestamp_utc for f in result.frames]
        assert timestamps == sorted(timestamps)

    def test_frame_index_sequential(self) -> None:
        events = _make_events(5)
        result = generate_single_case_replay("case-001", events)
        indices = [f.frame_index for f in result.frames]
        assert indices == [0, 1, 2, 3, 4]

    def test_each_frame_corresponds_to_one_event(self) -> None:
        events = _make_events(3)
        result = generate_single_case_replay("case-001", events)
        for i, frame in enumerate(result.frames):
            assert frame.activity_name == events[i]["activity_name"]

    def test_task_id_returned(self) -> None:
        events = _make_events(2)
        result = generate_single_case_replay("case-001", events)
        assert result.task_id
        # Should be valid UUID
        uuid.UUID(result.task_id)

    def test_status_completed(self) -> None:
        events = _make_events(2)
        result = generate_single_case_replay("case-001", events)
        assert result.status == "completed"

    def test_empty_events_returns_zero_frames(self) -> None:
        result = generate_single_case_replay("case-empty", [])
        assert result.total_frames == 0
        assert result.status == "completed"
        assert result.frames == []


# -- Scenario 2: Frame Content Completeness ----------------------------------


class TestFrameContentCompleteness:
    """Scenario 2: Each frame contains all required fields."""

    def test_frame_has_activity_name(self) -> None:
        events = [_make_event(activity="Submit Application")]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].activity_name == "Submit Application"

    def test_frame_has_performer(self) -> None:
        events = [_make_event(performer="Senior Analyst")]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].performer == "Senior Analyst"

    def test_frame_has_timestamp_utc(self) -> None:
        events = [_make_event(timestamp="2026-01-15T10:30:00+00:00")]
        result = generate_single_case_replay("case-001", events)
        assert "2026-01-15T10:30:00" in result.frames[0].timestamp_utc

    def test_frame_has_confidence_score(self) -> None:
        events = [_make_event(confidence=0.92)]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].confidence_score == 0.92

    def test_frame_has_evidence_refs(self) -> None:
        ref_id = str(uuid.uuid4())
        events = [_make_event(evidence_refs=[ref_id])]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].evidence_refs == [ref_id]

    def test_frame_has_brightness(self) -> None:
        events = [_make_event(confidence=0.85)]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].brightness == "bright"

    def test_frame_to_dict_complete(self) -> None:
        events = [_make_event()]
        result = generate_single_case_replay("case-001", events)
        d = result.frames[0].to_dict()
        required_keys = {
            "frame_index",
            "activity_name",
            "performer",
            "timestamp_utc",
            "confidence_score",
            "brightness",
            "evidence_refs",
        }
        assert required_keys <= set(d.keys())

    def test_null_performer_defaults_to_empty_string(self) -> None:
        events = [_make_event(performer=None)]  # type: ignore[arg-type]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].performer == ""

    def test_null_evidence_refs_defaults_to_empty_list(self) -> None:
        events = [_make_event(evidence_refs=None)]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].evidence_refs == []


# -- Scenario 3: Paginated Frame Retrieval -----------------------------------


class TestPaginatedFrameRetrieval:
    """Scenario 3: Paginated frames with metadata."""

    def test_first_page_of_10(self) -> None:
        events = _make_events(10)
        result = generate_single_case_replay("case-001", events)
        page = get_paginated_frames(result, limit=5, offset=0)
        assert len(page["frames"]) == 5
        assert page["total"] == 10
        assert page["has_more"] is True

    def test_second_page_of_10(self) -> None:
        events = _make_events(10)
        result = generate_single_case_replay("case-001", events)
        page = get_paginated_frames(result, limit=5, offset=5)
        assert len(page["frames"]) == 5
        assert page["has_more"] is False

    def test_pagination_metadata_fields(self) -> None:
        events = _make_events(10)
        result = generate_single_case_replay("case-001", events)
        page = get_paginated_frames(result, limit=5, offset=0)
        assert "total" in page
        assert "limit" in page
        assert "offset" in page
        assert "has_more" in page

    def test_offset_beyond_total(self) -> None:
        events = _make_events(5)
        result = generate_single_case_replay("case-001", events)
        page = get_paginated_frames(result, limit=5, offset=10)
        assert len(page["frames"]) == 0
        assert page["has_more"] is False

    def test_partial_last_page(self) -> None:
        events = _make_events(7)
        result = generate_single_case_replay("case-001", events)
        page = get_paginated_frames(result, limit=5, offset=5)
        assert len(page["frames"]) == 2
        assert page["has_more"] is False

    def test_task_id_in_response(self) -> None:
        events = _make_events(3)
        result = generate_single_case_replay("case-001", events)
        page = get_paginated_frames(result, limit=10, offset=0)
        assert page["task_id"] == result.task_id

    def test_limit_equals_total(self) -> None:
        events = _make_events(5)
        result = generate_single_case_replay("case-001", events)
        page = get_paginated_frames(result, limit=5, offset=0)
        assert len(page["frames"]) == 5
        assert page["has_more"] is False


# -- Scenario 4: Dark Segment Visual Flagging ---------------------------------


class TestDarkSegmentFlagging:
    """Scenario 4: Frames with confidence < 0.4 flagged as dark."""

    def test_low_confidence_is_dark(self) -> None:
        events = [_make_event(confidence=0.2)]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].brightness == "dark"

    def test_zero_confidence_is_dark(self) -> None:
        events = [_make_event(confidence=0.0)]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].brightness == "dark"

    def test_boundary_039_is_dark(self) -> None:
        events = [_make_event(confidence=0.39)]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].brightness == "dark"

    def test_boundary_040_is_dim(self) -> None:
        events = [_make_event(confidence=0.40)]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].brightness == "dim"

    def test_medium_confidence_is_dim(self) -> None:
        events = [_make_event(confidence=0.55)]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].brightness == "dim"

    def test_boundary_069_is_dim(self) -> None:
        events = [_make_event(confidence=0.69)]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].brightness == "dim"

    def test_boundary_070_is_bright(self) -> None:
        events = [_make_event(confidence=0.70)]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].brightness == "bright"

    def test_high_confidence_is_bright(self) -> None:
        events = [_make_event(confidence=0.95)]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].brightness == "bright"

    def test_dark_flag_in_dict_payload(self) -> None:
        events = [_make_event(confidence=0.2)]
        result = generate_single_case_replay("case-001", events)
        d = result.frames[0].to_dict()
        assert d["brightness"] == "dark"

    def test_existing_brightness_preserved(self) -> None:
        """If event already has brightness from CanonicalActivityEvent, use it."""
        events = [_make_event(confidence=0.85, brightness="dim")]
        result = generate_single_case_replay("case-001", events)
        # Existing brightness takes precedence
        assert result.frames[0].brightness == "dim"

    def test_mixed_brightness_in_case(self) -> None:
        events = [
            _make_event(activity="Step A", confidence=0.2, timestamp="2026-01-15T10:00:00+00:00"),
            _make_event(activity="Step B", confidence=0.55, timestamp="2026-01-15T11:00:00+00:00"),
            _make_event(activity="Step C", confidence=0.85, timestamp="2026-01-15T12:00:00+00:00"),
        ]
        result = generate_single_case_replay("case-001", events)
        assert result.frames[0].brightness == "dark"
        assert result.frames[1].brightness == "dim"
        assert result.frames[2].brightness == "bright"


# -- classify_brightness unit tests -------------------------------------------


class TestClassifyBrightness:
    """Unit tests for the brightness classification function."""

    def test_dark_below_threshold(self) -> None:
        assert classify_brightness(0.1) == "dark"

    def test_dim_in_range(self) -> None:
        assert classify_brightness(0.5) == "dim"

    def test_bright_above_threshold(self) -> None:
        assert classify_brightness(0.8) == "bright"

    def test_exact_dark_boundary(self) -> None:
        assert classify_brightness(0.4) == "dim"

    def test_exact_bright_boundary(self) -> None:
        assert classify_brightness(0.7) == "bright"


# -- SingleCaseReplayResult tests --------------------------------------------


class TestSingleCaseReplayResult:
    """Unit tests for the result dataclass."""

    def test_auto_generated_task_id(self) -> None:
        result = SingleCaseReplayResult(case_id="c1")
        assert result.task_id
        uuid.UUID(result.task_id)

    def test_auto_generated_created_at(self) -> None:
        result = SingleCaseReplayResult(case_id="c1")
        assert result.created_at
        assert "2026" in result.created_at

    def test_status_dict_format(self) -> None:
        result = SingleCaseReplayResult(case_id="c1", status="completed")
        d = result.to_status_dict()
        assert d["replay_type"] == "single_case"
        assert d["status"] == "completed"
        assert d["progress_pct"] == 100

    def test_pending_status_dict_progress_zero(self) -> None:
        result = SingleCaseReplayResult(case_id="c1", status="pending")
        d = result.to_status_dict()
        assert d["progress_pct"] == 0

    def test_case_id_stored(self) -> None:
        result = SingleCaseReplayResult(case_id="case-xyz")
        assert result.case_id == "case-xyz"


# -- build_frames_from_events edge cases -------------------------------------


class TestBuildFramesEdgeCases:
    """Edge case tests for frame building."""

    def test_datetime_object_converted_to_string(self) -> None:
        from datetime import UTC, datetime

        ts = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
        events = [_make_event()]
        events[0]["timestamp_utc"] = ts
        frames = build_frames_from_events(events)
        assert isinstance(frames[0].timestamp_utc, str)

    def test_missing_confidence_defaults_to_zero(self) -> None:
        events = [{"activity_name": "Step", "timestamp_utc": "2026-01-15T10:00:00Z"}]
        frames = build_frames_from_events(events)
        assert frames[0].confidence_score == 0.0
        assert frames[0].brightness == "dark"

    def test_uuid_evidence_refs_converted_to_strings(self) -> None:
        ref = uuid.uuid4()
        events = [_make_event(evidence_refs=[ref])]  # type: ignore[list-item]
        frames = build_frames_from_events(events)
        assert frames[0].evidence_refs == [str(ref)]

    def test_empty_events_returns_empty_list(self) -> None:
        frames = build_frames_from_events([])
        assert frames == []
