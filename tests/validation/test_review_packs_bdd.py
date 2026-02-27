"""BDD tests for Story #349: Review Pack Generation Engine.

Covers all 4 acceptance scenarios:
1. Activity segmentation into 3-8 activity groups
2. Review pack contents (evidence, confidence, conflicts, seed terms)
3. SME routing by role-activity mapping
4. Async generation API (HTTP 202 with task_id)
"""

from __future__ import annotations

import pytest

from src.validation.pack_generator import (
    ActivityInfo,
    ReviewPackData,
    determine_primary_role,
    generate_packs,
    segment_activities,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_activities(
    count: int,
    *,
    role: str | None = None,
    lane: str | None = None,
    confidence: float = 0.85,
    evidence_ids: list[str] | None = None,
    conflict_ids: list[str] | None = None,
    seed_term_ids: list[str] | None = None,
) -> list[ActivityInfo]:
    """Generate N activities for testing."""
    return [
        ActivityInfo(
            id=f"act-{i}",
            name=f"Activity {i}",
            confidence_score=confidence,
            evidence_ids=evidence_ids or [f"ev-{i}"],
            conflict_ids=conflict_ids or [],
            seed_term_ids=seed_term_ids or [f"st-{i}"],
            performing_role=role,
            lane=lane,
        )
        for i in range(count)
    ]


# ===========================================================================
# Scenario 1: Activity Segmentation
# ===========================================================================


class TestActivitySegmentation:
    """Scenario 1: Activities are grouped into segments of 3-8 activities each."""

    def test_30_activities_produce_reasonable_packs(self) -> None:
        """Given a POV with 30 activities, When segmented, Then packs are produced within bounds."""
        activities = _make_activities(30)
        segments = segment_activities(activities)

        # Algorithm targets 5 activities/segment. With max_size=8 it may
        # produce fewer, larger segments (e.g. 4 segments of 7-8).
        assert 3 <= len(segments) <= 10
        total = sum(len(s) for s in segments)
        assert total == 30

    def test_all_segments_within_size_bounds(self) -> None:
        """Every segment should contain 3-8 activities."""
        activities = _make_activities(30)
        segments = segment_activities(activities)

        for segment in segments:
            assert 3 <= len(segment) <= 8, f"Segment has {len(segment)} activities, expected 3-8"

    def test_no_activity_excluded(self) -> None:
        """No activity should be excluded from a pack."""
        activities = _make_activities(30)
        segments = segment_activities(activities)

        all_ids = [a.id for segment in segments for a in segment]
        expected_ids = [f"act-{i}" for i in range(30)]
        assert sorted(all_ids) == sorted(expected_ids)

    def test_exactly_3_activities(self) -> None:
        """Edge case: POV with exactly 3 activities → 1 segment."""
        activities = _make_activities(3)
        segments = segment_activities(activities)

        assert len(segments) == 1
        assert len(segments[0]) == 3

    def test_exactly_8_activities(self) -> None:
        """Edge case: POV with exactly 8 activities → 1 segment."""
        activities = _make_activities(8)
        segments = segment_activities(activities)

        assert len(segments) == 1
        assert len(segments[0]) == 8

    def test_9_activities_produce_2_segments(self) -> None:
        """9 activities should produce 2 segments (within 3-8 each)."""
        activities = _make_activities(9)
        segments = segment_activities(activities)

        assert len(segments) == 2
        for segment in segments:
            assert 3 <= len(segment) <= 8

    def test_empty_activities(self) -> None:
        """Edge case: no activities → no segments."""
        segments = segment_activities([])
        assert segments == []

    def test_1_activity(self) -> None:
        """Edge case: 1 activity → 1 segment (below min but only option)."""
        activities = _make_activities(1)
        segments = segment_activities(activities)

        assert len(segments) == 1
        assert len(segments[0]) == 1


# ===========================================================================
# Scenario 2: Review Pack Contents
# ===========================================================================


class TestReviewPackContents:
    """Scenario 2: Each pack contains evidence, confidence, conflicts, seed terms."""

    def test_pack_contains_evidence_list(self) -> None:
        """Pack should aggregate evidence IDs from all activities in the segment."""
        activities = _make_activities(5, evidence_ids=["ev-shared"])
        packs = generate_packs(activities)

        assert len(packs) == 1
        assert "ev-shared" in packs[0].evidence_ids

    def test_pack_contains_per_element_confidence_scores(self) -> None:
        """Pack should have confidence score for each activity."""
        activities = _make_activities(5, confidence=0.92)
        packs = generate_packs(activities)

        assert len(packs[0].confidence_scores) == 5
        for score in packs[0].confidence_scores.values():
            assert score == 0.92

    def test_pack_contains_conflict_flags(self) -> None:
        """Pack should include ConflictObject flags from activities."""
        activities = _make_activities(5, conflict_ids=["conflict-1", "conflict-2"])
        packs = generate_packs(activities)

        assert "conflict-1" in packs[0].conflict_ids
        assert "conflict-2" in packs[0].conflict_ids

    def test_pack_contains_seed_terms(self) -> None:
        """Pack should include related seed list terms."""
        activities = _make_activities(5, seed_term_ids=["term-1"])
        packs = generate_packs(activities)

        assert "term-1" in packs[0].seed_term_ids

    def test_pack_has_avg_confidence(self) -> None:
        """Pack should have average confidence across its activities."""
        activities = _make_activities(4, confidence=0.8)
        packs = generate_packs(activities)

        assert packs[0].avg_confidence == pytest.approx(0.8, abs=0.01)

    def test_evidence_ids_are_deduplicated(self) -> None:
        """Duplicate evidence IDs should be removed."""
        activities = _make_activities(5, evidence_ids=["ev-dup"])
        packs = generate_packs(activities)

        # All 5 activities have "ev-dup", should appear once in deduped list
        assert packs[0].evidence_ids.count("ev-dup") == 1

    def test_conflict_ids_are_deduplicated(self) -> None:
        """Duplicate conflict IDs should be removed."""
        activities = _make_activities(5, conflict_ids=["c-dup"])
        packs = generate_packs(activities)

        assert packs[0].conflict_ids.count("c-dup") == 1


# ===========================================================================
# Scenario 3: SME Routing by Role-Activity Mapping
# ===========================================================================


class TestSMERouting:
    """Scenario 3: Packs are routed to SMEs by role-activity mapping."""

    def test_pack_assigned_to_primary_role(self) -> None:
        """Pack should be assigned to the most common role in the segment."""
        activities = _make_activities(5, role="Operations Manager")
        packs = generate_packs(activities)

        assert packs[0].assigned_role == "Operations Manager"

    def test_majority_role_wins_assignment(self) -> None:
        """When mixed roles, the most frequent role is assigned."""
        activities = [
            ActivityInfo(id="a1", name="A1", performing_role="Ops Manager"),
            ActivityInfo(id="a2", name="A2", performing_role="Ops Manager"),
            ActivityInfo(id="a3", name="A3", performing_role="Ops Manager"),
            ActivityInfo(id="a4", name="A4", performing_role="Analyst"),
            ActivityInfo(id="a5", name="A5", performing_role="Analyst"),
        ]
        packs = generate_packs(activities)

        assert packs[0].assigned_role == "Ops Manager"

    def test_no_role_returns_none(self) -> None:
        """When no activities have a role, assigned_role is None."""
        activities = _make_activities(5, role=None)
        packs = generate_packs(activities)

        assert packs[0].assigned_role is None

    def test_determine_primary_role_single(self) -> None:
        """A single role should be returned."""
        activities = _make_activities(3, role="Reviewer")
        result = determine_primary_role(activities)
        assert result == "Reviewer"

    def test_determine_primary_role_empty(self) -> None:
        """No roles → None."""
        result = determine_primary_role([])
        assert result is None


# ===========================================================================
# Scenario 4: Async Generation API
# ===========================================================================


class TestAsyncGeneration:
    """Scenario 4: POST returns 202 with task_id, GET retrieves packs."""

    def test_generate_response_schema(self) -> None:
        """Generate endpoint response should have task_id and status fields."""
        from src.api.routes.validation import GenerateResponse

        fields = GenerateResponse.model_fields
        assert "task_id" in fields
        assert "status" in fields
        assert "message" in fields

    def test_generate_request_schema(self) -> None:
        """Generate request should require pov_version_id and engagement_id."""
        from src.api.routes.validation import GenerateRequest

        fields = GenerateRequest.model_fields
        assert "pov_version_id" in fields
        assert "engagement_id" in fields

    def test_review_pack_response_schema(self) -> None:
        """ReviewPackResponse should have all required fields."""
        from src.api.routes.validation import ReviewPackResponse

        fields = ReviewPackResponse.model_fields
        assert "id" in fields
        assert "engagement_id" in fields
        assert "pov_version_id" in fields
        assert "segment_index" in fields
        assert "segment_activities" in fields
        assert "evidence_list" in fields
        assert "confidence_scores" in fields
        assert "conflict_flags" in fields
        assert "seed_terms" in fields
        assert "assigned_role" in fields
        assert "status" in fields
        assert "avg_confidence" in fields

    def test_paginated_response_schema(self) -> None:
        """Paginated response should have items, total, limit, offset."""
        from src.api.routes.validation import PaginatedReviewPackResponse

        fields = PaginatedReviewPackResponse.model_fields
        assert "items" in fields
        assert "total" in fields
        assert "limit" in fields
        assert "offset" in fields

    def test_router_prefix(self) -> None:
        """Router should be at /api/v1/validation."""
        from src.api.routes.validation import router

        assert router.prefix == "/api/v1/validation"

    def test_router_tag(self) -> None:
        """Router should have 'validation' tag."""
        from src.api.routes.validation import router

        assert "validation" in router.tags


# ===========================================================================
# Pack generation edge cases and dataclass tests
# ===========================================================================


class TestReviewPackData:
    """Test the ReviewPackData dataclass."""

    def test_default_values(self) -> None:
        d = ReviewPackData()
        assert d.segment_index == 0
        assert d.activities == []
        assert d.evidence_ids == []
        assert d.avg_confidence == 0.0

    def test_segment_index_ordering(self) -> None:
        """Packs should have sequential segment indices."""
        activities = _make_activities(20)
        packs = generate_packs(activities)

        indices = [p.segment_index for p in packs]
        assert indices == list(range(len(packs)))


class TestActivityInfo:
    """Test the ActivityInfo dataclass."""

    def test_default_values(self) -> None:
        a = ActivityInfo()
        assert a.id == ""
        assert a.name == ""
        assert a.confidence_score == 0.0
        assert a.performing_role is None
        assert a.lane is None

    def test_custom_values(self) -> None:
        a = ActivityInfo(
            id="act-1",
            name="Review Application",
            confidence_score=0.95,
            evidence_ids=["ev-1", "ev-2"],
            performing_role="Analyst",
            lane="Back Office",
        )
        assert a.id == "act-1"
        assert a.performing_role == "Analyst"
        assert a.lane == "Back Office"
        assert len(a.evidence_ids) == 2


class TestModelStructure:
    """Test ReviewPack model structure."""

    def test_tablename(self) -> None:
        from src.core.models.validation import ReviewPack

        assert ReviewPack.__tablename__ == "review_packs"

    def test_has_engagement_index(self) -> None:
        from src.core.models.validation import ReviewPack

        names = [c.name for c in ReviewPack.__table_args__ if hasattr(c, "name") and c.name]
        assert "ix_review_packs_engagement_id" in names

    def test_has_pov_version_index(self) -> None:
        from src.core.models.validation import ReviewPack

        names = [c.name for c in ReviewPack.__table_args__ if hasattr(c, "name") and c.name]
        assert "ix_review_packs_pov_version_id" in names

    def test_status_enum_values(self) -> None:
        from src.core.models.validation import ReviewPackStatus

        assert ReviewPackStatus.PENDING == "pending"
        assert ReviewPackStatus.SENT == "sent"
        assert ReviewPackStatus.IN_REVIEW == "in_review"
        assert ReviewPackStatus.COMPLETE == "complete"


class TestMigration043Structure:
    """Test migration 043 module structure."""

    @staticmethod
    def _load_migration():
        import importlib.util
        import pathlib

        path = pathlib.Path("alembic/versions/043_review_packs.py")
        spec = importlib.util.spec_from_file_location("migration_043", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_migration_revision(self) -> None:
        mod = self._load_migration()
        assert mod.revision == "043"
        assert mod.down_revision == "042"

    def test_migration_has_upgrade_and_downgrade(self) -> None:
        mod = self._load_migration()
        assert hasattr(mod, "upgrade")
        assert hasattr(mod, "downgrade")
