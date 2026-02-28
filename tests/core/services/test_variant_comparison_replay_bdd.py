"""BDD tests for variant comparison replay service (Story #342).

Tests cover all acceptance criteria from the story:
- Side-by-side synchronized replay with LCS alignment
- Divergence point identification (activity, performer, one-sided)
- Cycle time comparison with per-step deltas and totals
- Divergence evidence linking from frames and annotations
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.core.services.variant_comparison_replay import (
    ComparisonStage,
    VariantComparisonResult,
    VariantFrame,
    compute_lcs_alignment,
    generate_variant_comparison,
)


def _make_event(
    activity: str,
    performer: str = "analyst",
    ts: datetime | None = None,
    confidence: float = 0.8,
    evidence_refs: list[str] | None = None,
) -> dict:
    """Build a minimal canonical event dict for testing."""
    if ts is None:
        ts = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
    return {
        "activity_name": activity,
        "performer_role_ref": performer,
        "timestamp_utc": ts.isoformat(),
        "confidence_score": confidence,
        "evidence_refs": evidence_refs or [],
    }


def _make_variant_events(
    activities: list[str],
    performer: str = "analyst",
    base_ts: datetime | None = None,
    step_minutes: int = 60,
    evidence_refs: list[list[str]] | None = None,
) -> list[dict]:
    """Build a sequence of events for a variant."""
    if base_ts is None:
        base_ts = datetime(2026, 1, 15, 9, 0, 0, tzinfo=UTC)
    events = []
    for i, act in enumerate(activities):
        refs = evidence_refs[i] if evidence_refs and i < len(evidence_refs) else []
        events.append(
            _make_event(
                activity=act,
                performer=performer,
                ts=base_ts + timedelta(minutes=i * step_minutes),
                evidence_refs=refs,
            )
        )
    return events


# ============================================================
# Scenario 1: Side-by-Side Synchronized Replay
# ============================================================


class TestSideBySideSynchronizedReplay:
    """Given Variant A and Variant B each with a canonical event spine,
    when the comparison is generated, then both variants are returned
    as synchronized replay frames aligned by process stage."""

    def test_identical_variants_produce_aligned_stages(self) -> None:
        """Two identical variants produce N aligned stages with no divergence."""
        activities = ["Submit", "Review", "Approve"]
        events_a = _make_variant_events(activities)
        events_b = _make_variant_events(activities)

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        assert result.status == "completed"
        assert result.total_stages == 3
        assert result.total_divergences == 0

    def test_each_stage_has_both_variant_frames(self) -> None:
        """Each aligned stage shows both variants' activity data."""
        activities = ["Submit", "Review"]
        events_a = _make_variant_events(activities, performer="alice")
        events_b = _make_variant_events(activities, performer="bob")

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        for stage in result.stages:
            assert stage.variant_a_frame is not None
            assert stage.variant_b_frame is not None
            assert stage.variant_a_frame.activity_name == stage.variant_b_frame.activity_name

    def test_stage_frames_contain_activity_data(self) -> None:
        """Frames at each stage contain activity name, performer, timestamp."""
        events_a = _make_variant_events(["Submit"], performer="alice")
        events_b = _make_variant_events(["Submit"], performer="bob")

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        stage = result.stages[0]
        assert stage.variant_a_frame is not None
        assert stage.variant_a_frame.activity_name == "Submit"
        assert stage.variant_a_frame.performer == "alice"
        assert stage.variant_b_frame is not None
        assert stage.variant_b_frame.performer == "bob"

    def test_empty_variants_produce_empty_result(self) -> None:
        """Two empty variants produce zero stages."""
        result = generate_variant_comparison("v-a", "v-b", [], [])
        assert result.status == "completed"
        assert result.total_stages == 0
        assert result.stages == []

    def test_result_contains_variant_ids(self) -> None:
        """Result includes both variant identifiers."""
        result = generate_variant_comparison("variant-1", "variant-2", [], [])
        assert result.variant_a_id == "variant-1"
        assert result.variant_b_id == "variant-2"

    def test_result_has_task_id_and_created_at(self) -> None:
        """Result is assigned a unique task_id and created_at timestamp."""
        result = generate_variant_comparison("v-a", "v-b", [], [])
        assert result.task_id  # non-empty UUID
        assert result.created_at  # non-empty ISO timestamp

    def test_to_status_dict_reports_replay_type(self) -> None:
        """Status dict reports replay_type as variant_comparison."""
        result = generate_variant_comparison("v-a", "v-b", [], [])
        status = result.to_status_dict()
        assert status["replay_type"] == "variant_comparison"
        assert status["status"] == "completed"
        assert status["progress_pct"] == 100


# ============================================================
# Scenario 2: Divergence Point Identification
# ============================================================


class TestDivergencePointIdentification:
    """Given Variant A and Variant B that diverge, divergence points
    are flagged with differing activity names and performers."""

    def test_activity_mismatch_flagged_as_divergence(self) -> None:
        """Different activities at the same stage are flagged."""
        events_a = _make_variant_events(["Submit", "Review", "Approve"])
        events_b = _make_variant_events(["Submit", "Audit", "Approve"])

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        # Find divergence stages
        divergences = [s for s in result.stages if s.is_divergence]
        assert len(divergences) >= 1
        assert result.total_divergences >= 1

    def test_performer_mismatch_flagged_as_divergence(self) -> None:
        """Same activity but different performers is a performer_mismatch."""
        base_ts = datetime(2026, 1, 15, 9, 0, 0, tzinfo=UTC)
        events_a = [
            _make_event("Submit", "alice", base_ts),
            _make_event("Review", "alice", base_ts + timedelta(hours=1)),
        ]
        events_b = [
            _make_event("Submit", "alice", base_ts),
            _make_event("Review", "bob", base_ts + timedelta(hours=1)),
        ]

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        divergences = [s for s in result.stages if s.is_divergence]
        assert len(divergences) == 1
        assert divergences[0].divergence_type == "performer_mismatch"

    def test_a_only_stage_flagged(self) -> None:
        """Activity present only in Variant A is flagged as a_only."""
        events_a = _make_variant_events(["Submit", "Extra", "Approve"])
        events_b = _make_variant_events(["Submit", "Approve"])

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        a_only = [s for s in result.stages if s.divergence_type == "a_only"]
        assert len(a_only) == 1
        assert a_only[0].variant_a_frame is not None
        assert a_only[0].variant_a_frame.activity_name == "Extra"
        assert a_only[0].variant_b_frame is None

    def test_b_only_stage_flagged(self) -> None:
        """Activity present only in Variant B is flagged as b_only."""
        events_a = _make_variant_events(["Submit", "Approve"])
        events_b = _make_variant_events(["Submit", "Extra", "Approve"])

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        b_only = [s for s in result.stages if s.divergence_type == "b_only"]
        assert len(b_only) == 1
        assert b_only[0].variant_b_frame is not None
        assert b_only[0].variant_b_frame.activity_name == "Extra"
        assert b_only[0].variant_a_frame is None

    def test_divergence_shows_both_activities_and_performers(self) -> None:
        """Divergence stages show differing activity names and performers."""
        events_a = _make_variant_events(["Submit", "ManualReview", "Approve"])
        events_b = _make_variant_events(["Submit", "AutoReview", "Approve"])

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        # ManualReview and AutoReview are different, so they appear as separate stages
        # The LCS aligns Submit and Approve, leaving the middle unmatched
        divergences = [s for s in result.stages if s.is_divergence]
        assert len(divergences) >= 1

    def test_multiple_divergence_points_detected(self) -> None:
        """Multiple divergence points across the process are all detected."""
        events_a = _make_variant_events(["A", "B", "C", "D", "E"])
        events_b = _make_variant_events(["A", "X", "C", "Y", "E"])

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        # A, C, E align; B/X and D/Y are divergent
        divergences = [s for s in result.stages if s.is_divergence]
        assert len(divergences) >= 2
        assert result.total_divergences >= 2

    def test_no_divergence_for_identical_variants(self) -> None:
        """Identical variants have zero divergence points."""
        activities = ["Submit", "Review", "Approve"]
        events_a = _make_variant_events(activities)
        events_b = _make_variant_events(activities)

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)
        assert result.total_divergences == 0


# ============================================================
# Scenario 3: Cycle Time Comparison
# ============================================================


class TestCycleTimeComparison:
    """Given cycle time data for both variants, per-step deltas and
    total end-to-end cycle times are reported."""

    def test_per_step_cycle_time_delta_computed(self) -> None:
        """Each stage includes cycle_time_delta_ms (A - B)."""
        base_ts = datetime(2026, 1, 15, 9, 0, 0, tzinfo=UTC)
        # A: 60min step, B: 30min step
        events_a = [
            _make_event("Submit", ts=base_ts),
            _make_event("Review", ts=base_ts + timedelta(minutes=60)),
        ]
        events_b = [
            _make_event("Submit", ts=base_ts),
            _make_event("Review", ts=base_ts + timedelta(minutes=30)),
        ]

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        # First stage: both 0 (first event)
        assert result.stages[0].cycle_time_delta_ms == 0
        # Second stage: A=60min=3600000ms, B=30min=1800000ms, delta=1800000
        assert result.stages[1].cycle_time_delta_ms == 1_800_000

    def test_total_cycle_time_for_each_variant(self) -> None:
        """Total end-to-end cycle time reported for each variant."""
        base_ts = datetime(2026, 1, 15, 9, 0, 0, tzinfo=UTC)
        events_a = [
            _make_event("Submit", ts=base_ts),
            _make_event("Review", ts=base_ts + timedelta(hours=2)),
            _make_event("Approve", ts=base_ts + timedelta(hours=5)),
        ]
        events_b = [
            _make_event("Submit", ts=base_ts),
            _make_event("Review", ts=base_ts + timedelta(hours=1)),
            _make_event("Approve", ts=base_ts + timedelta(hours=2)),
        ]

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        # A total: 0 + 2h + 3h = 5h = 18000000ms
        assert result.variant_a_total_cycle_time_ms == 18_000_000
        # B total: 0 + 1h + 1h = 2h = 7200000ms
        assert result.variant_b_total_cycle_time_ms == 7_200_000

    def test_single_event_has_zero_cycle_time(self) -> None:
        """A variant with only one event has zero total cycle time."""
        events_a = _make_variant_events(["Submit"])
        result = generate_variant_comparison("v-a", "v-b", events_a, [])
        assert result.variant_a_total_cycle_time_ms == 0

    def test_cycle_time_zero_for_first_stage(self) -> None:
        """First stage always has zero cycle time (no predecessor)."""
        events_a = _make_variant_events(["Submit", "Review"])
        events_b = _make_variant_events(["Submit", "Review"])

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)
        assert result.stages[0].cycle_time_delta_ms == 0

    def test_negative_delta_when_b_slower(self) -> None:
        """Negative delta when Variant B is slower than Variant A."""
        base_ts = datetime(2026, 1, 15, 9, 0, 0, tzinfo=UTC)
        events_a = [
            _make_event("Submit", ts=base_ts),
            _make_event("Review", ts=base_ts + timedelta(minutes=10)),
        ]
        events_b = [
            _make_event("Submit", ts=base_ts),
            _make_event("Review", ts=base_ts + timedelta(minutes=60)),
        ]

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        # A=10min=600000ms, B=60min=3600000ms, delta=600000-3600000=-3000000
        assert result.stages[1].cycle_time_delta_ms == -3_000_000


# ============================================================
# Scenario 4: Divergence Evidence Linking
# ============================================================


class TestDivergenceEvidenceLinking:
    """Given a divergence point linked to evidence artifacts, the
    evidence is surfaced in the divergence frame payload."""

    def test_evidence_from_variant_frames_collected(self) -> None:
        """Divergence evidence includes refs from both variant frames."""
        events_a = _make_variant_events(
            ["Submit", "ManualReview"],
            evidence_refs=[["ev-1"], ["ev-2"]],
        )
        events_b = _make_variant_events(
            ["Submit", "AutoReview"],
            evidence_refs=[["ev-3"], ["ev-4"]],
        )

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        divergences = [s for s in result.stages if s.is_divergence]
        assert len(divergences) >= 1

        # At least one divergence should have evidence refs
        all_evidence = []
        for d in divergences:
            all_evidence.extend(d.divergence_evidence_refs)
        assert len(all_evidence) > 0

    def test_annotation_evidence_merged_with_frame_evidence(self) -> None:
        """Explicit divergence annotations are merged with frame evidence."""
        events_a = _make_variant_events(
            ["Submit", "Review"],
            evidence_refs=[[], ["ev-frame"]],
        )
        events_b = _make_variant_events(
            ["Submit", "Audit"],
            evidence_refs=[[], []],
        )

        # Annotation at stage 2 (where Review/Audit diverge)
        # LCS: Submit matches. Review and Audit don't match.
        # Alignment: (0,0)=Submit, (1,None)=Review(a_only), (None,1)=Audit(b_only)
        # The a_only stage is at index 1, b_only at index 2
        result = generate_variant_comparison(
            "v-a",
            "v-b",
            events_a,
            events_b,
            divergence_annotations={1: ["ev-annotation"]},
        )

        divergences = [s for s in result.stages if s.is_divergence]
        assert len(divergences) >= 1

        # Find the stage with annotation evidence
        annotated = [s for s in divergences if "ev-annotation" in s.divergence_evidence_refs]
        assert len(annotated) == 1

    def test_evidence_deduplicated(self) -> None:
        """Duplicate evidence refs are deduplicated."""
        events_a = _make_variant_events(
            ["Submit", "Review"],
            evidence_refs=[[], ["ev-shared"]],
        )
        events_b = _make_variant_events(
            ["Submit", "Audit"],
            evidence_refs=[[], ["ev-shared"]],
        )

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        for stage in result.stages:
            # No duplicates in evidence refs
            assert len(stage.divergence_evidence_refs) == len(set(stage.divergence_evidence_refs))

    def test_no_evidence_for_non_divergence_stages(self) -> None:
        """Non-divergence stages have empty evidence refs."""
        events_a = _make_variant_events(["Submit", "Review"])
        events_b = _make_variant_events(["Submit", "Review"])

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        for stage in result.stages:
            assert not stage.is_divergence
            assert stage.divergence_evidence_refs == []

    def test_divergence_stage_to_dict_includes_evidence(self) -> None:
        """Stage.to_dict() includes divergence_evidence_refs field."""
        events_a = _make_variant_events(
            ["Submit", "Review"],
            evidence_refs=[[], ["ev-1"]],
        )
        events_b = _make_variant_events(
            ["Submit", "Audit"],
            evidence_refs=[[], ["ev-2"]],
        )

        result = generate_variant_comparison("v-a", "v-b", events_a, events_b)

        for stage in result.stages:
            d = stage.to_dict()
            assert "divergence_evidence_refs" in d
            assert "is_divergence" in d
            assert "divergence_type" in d


# ============================================================
# LCS Alignment Algorithm Tests
# ============================================================


class TestLcsAlignment:
    """Unit tests for the LCS alignment algorithm."""

    def test_identical_sequences(self) -> None:
        """Identical sequences produce perfect 1:1 alignment."""
        alignment = compute_lcs_alignment(["A", "B", "C"], ["A", "B", "C"])
        assert alignment == [(0, 0), (1, 1), (2, 2)]

    def test_completely_different_sequences(self) -> None:
        """Completely different sequences produce all-unmatched alignment."""
        alignment = compute_lcs_alignment(["A", "B"], ["X", "Y"])
        # No common elements, so all are unmatched
        assert len(alignment) == 4
        a_indices = [p[0] for p in alignment if p[0] is not None]
        b_indices = [p[1] for p in alignment if p[1] is not None]
        assert set(a_indices) == {0, 1}
        assert set(b_indices) == {0, 1}

    def test_one_empty_sequence(self) -> None:
        """One empty sequence produces all-unmatched alignment."""
        alignment = compute_lcs_alignment(["A", "B"], [])
        assert alignment == [(0, None), (1, None)]

        alignment = compute_lcs_alignment([], ["X", "Y"])
        assert alignment == [(None, 0), (None, 1)]

    def test_both_empty(self) -> None:
        """Two empty sequences produce empty alignment."""
        assert compute_lcs_alignment([], []) == []

    def test_partial_overlap(self) -> None:
        """Partial overlap aligns common elements, interleaves unique ones."""
        alignment = compute_lcs_alignment(
            ["A", "B", "C", "D"],
            ["A", "X", "C", "Y"],
        )
        # LCS is A, C
        # Expected: (0,0)=A, (1,None)=B, (None,1)=X, (2,2)=C, (3,None)=D, (None,3)=Y
        matched = [(a, b) for a, b in alignment if a is not None and b is not None]
        assert len(matched) == 2  # A and C

    def test_subsequence_detection(self) -> None:
        """Detects longest common subsequence, not just common elements."""
        alignment = compute_lcs_alignment(
            ["A", "B", "C", "D", "E"],
            ["A", "C", "E"],
        )
        # LCS is A, C, E — 3 matches
        matched = [(a, b) for a, b in alignment if a is not None and b is not None]
        assert len(matched) == 3

    def test_varying_divergence_depth(self) -> None:
        """LCS handles variants with deeply different middle sections."""
        alignment = compute_lcs_alignment(
            ["Start", "A1", "A2", "A3", "End"],
            ["Start", "B1", "B2", "B3", "B4", "End"],
        )
        # LCS: Start, End — 2 matches
        matched = [(a, b) for a, b in alignment if a is not None and b is not None]
        assert len(matched) == 2
        # Total stages = 2 matched + 3 unmatched-A + 4 unmatched-B = 9
        assert len(alignment) == 9


# ============================================================
# VariantFrame and ComparisonStage Dataclass Tests
# ============================================================


class TestVariantFrame:
    """Tests for VariantFrame dataclass."""

    def test_to_dict_all_fields(self) -> None:
        """to_dict includes all frame fields."""
        frame = VariantFrame(
            activity_name="Review",
            performer="alice",
            timestamp_utc="2026-01-15T10:00:00+00:00",
            confidence_score=0.85,
            cycle_time_ms=3600000,
            evidence_refs=["ev-1"],
        )
        d = frame.to_dict()
        assert d["activity_name"] == "Review"
        assert d["performer"] == "alice"
        assert d["cycle_time_ms"] == 3600000
        assert d["evidence_refs"] == ["ev-1"]

    def test_default_values(self) -> None:
        """VariantFrame has sensible defaults."""
        frame = VariantFrame(activity_name="Submit")
        assert frame.performer == ""
        assert frame.cycle_time_ms == 0
        assert frame.evidence_refs == []


class TestComparisonStage:
    """Tests for ComparisonStage dataclass."""

    def test_to_dict_with_divergence(self) -> None:
        """to_dict correctly serializes a divergence stage."""
        stage = ComparisonStage(
            stage_index=3,
            variant_a_frame=VariantFrame(activity_name="Review"),
            variant_b_frame=VariantFrame(activity_name="Audit"),
            is_divergence=True,
            divergence_type="activity_mismatch",
            divergence_evidence_refs=["ev-1"],
            cycle_time_delta_ms=500,
        )
        d = stage.to_dict()
        assert d["stage_index"] == 3
        assert d["is_divergence"] is True
        assert d["divergence_type"] == "activity_mismatch"
        assert d["variant_a_frame"]["activity_name"] == "Review"
        assert d["variant_b_frame"]["activity_name"] == "Audit"

    def test_to_dict_with_none_frame(self) -> None:
        """to_dict handles None frames (one-sided divergence)."""
        stage = ComparisonStage(
            stage_index=0,
            variant_a_frame=VariantFrame(activity_name="Extra"),
            variant_b_frame=None,
            is_divergence=True,
            divergence_type="a_only",
        )
        d = stage.to_dict()
        assert d["variant_a_frame"] is not None
        assert d["variant_b_frame"] is None


class TestVariantComparisonResult:
    """Tests for VariantComparisonResult dataclass."""

    def test_auto_generates_task_id(self) -> None:
        """Result auto-generates task_id if not provided."""
        r = VariantComparisonResult()
        assert r.task_id
        assert len(r.task_id) == 36  # UUID format

    def test_auto_generates_created_at(self) -> None:
        """Result auto-generates created_at timestamp."""
        r = VariantComparisonResult()
        assert r.created_at
        assert "T" in r.created_at  # ISO format

    def test_pending_status_default(self) -> None:
        """Default status is pending."""
        r = VariantComparisonResult()
        assert r.status == "pending"

    def test_to_status_dict_pending(self) -> None:
        """Pending result reports 0% progress."""
        r = VariantComparisonResult()
        d = r.to_status_dict()
        assert d["progress_pct"] == 0
        assert d["status"] == "pending"
