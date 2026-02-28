"""BDD tests for Persona-Specific Dashboards API endpoints (Story #362).

Tests the four persona dashboards: Engagement Lead, Process Analyst, SME,
and Client Stakeholder with role-based access control.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.routes.dashboard import (
    BrightnessDistribution,
    ClientStakeholderDashboard,
    ConflictQueueItem,
    EngagementLeadDashboard,
    GapFindingSummary,
    ProcessAnalystDashboard,
    ProcessingStatusCounts,
    SmeDashboard,
    TOMAlignmentEntry,
    _get_user_engagement_role,
    get_analyst_dashboard,
    get_client_dashboard,
    get_engagement_lead_dashboard,
    get_sme_dashboard,
)
from src.core.models import UserRole

# -- Fixtures ----------------------------------------------------------------


def _make_mock_user(
    role: UserRole = UserRole.PLATFORM_ADMIN,
    user_id: uuid.UUID | None = None,
) -> MagicMock:
    """Create a mock user."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.role = role
    return user


def _engagement_exists_result() -> MagicMock:
    """Mock result for engagement existence check (returns a UUID)."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = uuid.uuid4()
    return result


def _engagement_not_found_result() -> MagicMock:
    """Mock result for engagement not found (returns None)."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    return result


def _mock_member_session(role_in_engagement: str) -> AsyncMock:
    """Create session mock that returns user as engagement member with given role.

    First query: engagement existence check (returns UUID).
    Second query: member role lookup (returns role string).
    """
    session = AsyncMock()
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = role_in_engagement
    session.execute = AsyncMock(side_effect=[_engagement_exists_result(), member_result])
    return session


def _mock_non_member_session() -> AsyncMock:
    """Create session mock that returns no engagement membership.

    First query: engagement existence check (returns UUID).
    Second query: member role lookup (returns None).
    """
    session = AsyncMock()
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(side_effect=[_engagement_exists_result(), member_result])
    return session


# ============================================================
# Role detection helper
# ============================================================


class TestRoleDetection:
    """Role detection for persona dashboards."""

    @pytest.mark.asyncio
    async def test_platform_admin_returns_platform_admin_role(self) -> None:
        """Platform admins bypass membership check but engagement must exist."""
        user = _make_mock_user(role=UserRole.PLATFORM_ADMIN)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_engagement_exists_result())

        role = await _get_user_engagement_role(uuid.uuid4(), user, session)

        assert role == "platform_admin"
        # Exactly one call: engagement existence check
        assert session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_member_returns_role(self) -> None:
        """Engagement member gets their role returned."""
        user = _make_mock_user(role=UserRole.ENGAGEMENT_LEAD)
        session = _mock_member_session("engagement_lead")

        role = await _get_user_engagement_role(uuid.uuid4(), user, session)

        assert role == "engagement_lead"

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self) -> None:
        """Non-member user gets 403."""
        from fastapi import HTTPException

        user = _make_mock_user(role=UserRole.ENGAGEMENT_LEAD)
        session = _mock_non_member_session()

        with pytest.raises(HTTPException) as exc_info:
            await _get_user_engagement_role(uuid.uuid4(), user, session)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_nonexistent_engagement_gets_404(self) -> None:
        """Request for nonexistent engagement returns 404, not 403."""
        from fastapi import HTTPException

        user = _make_mock_user(role=UserRole.ENGAGEMENT_LEAD)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_engagement_not_found_result())

        with pytest.raises(HTTPException) as exc_info:
            await _get_user_engagement_role(uuid.uuid4(), user, session)

        assert exc_info.value.status_code == 404


# ============================================================
# Scenario 1: Engagement Lead dashboard with full KPI suite
# ============================================================


class TestEngagementLeadDashboard:
    """GET /api/v1/dashboard/{id}/engagement-lead returns full KPIs."""

    @pytest.mark.asyncio
    async def test_returns_all_kpis(self) -> None:
        """Engagement Lead gets all KPIs: coverage, confidence, brightness, etc."""
        eng_id = uuid.uuid4()
        user = _make_mock_user()

        # Build mock session with sequential query responses
        session = AsyncMock()

        # 1. Engagement existence check (inside _get_user_engagement_role)
        eng_exists_result = _engagement_exists_result()

        # 2. Shelf coverage: total=10, received=7
        shelf_row = MagicMock()
        shelf_row.total = 10
        shelf_row.received = 7
        shelf_result = MagicMock()
        shelf_result.one.return_value = shelf_row

        # 3. Latest model
        latest_model = MagicMock()
        latest_model.id = uuid.uuid4()
        latest_model.confidence_score = 0.85
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = latest_model

        # 4. Brightness counts (model_id passed directly, no extra lookup)
        bright_row = MagicMock()
        bright_row.brightness_classification = "bright"
        bright_row.cnt = 6
        dim_row = MagicMock()
        dim_row.brightness_classification = "dim"
        dim_row.cnt = 3
        dark_row = MagicMock()
        dark_row.brightness_classification = "dark"
        dark_row.cnt = 1
        brightness_result = MagicMock()
        brightness_result.all.return_value = [bright_row, dim_row, dark_row]

        # 5. Gaps for TOM alignment (now returns row tuples, not ORM objects)
        gaps_result = MagicMock()
        gaps_result.all.return_value = []

        # 6. Gap severity counts
        gap_sev_result = MagicMock()
        gap_sev_result.all.return_value = []

        # 7. Seed term counts
        seed_row = MagicMock()
        seed_row.total = 20
        seed_row.active = 15
        seed_result = MagicMock()
        seed_result.one.return_value = seed_row

        # 8. Dark room snapshots
        snap1 = MagicMock()
        snap1.dark_count = 5
        snap1.version_number = 2
        snap2 = MagicMock()
        snap2.dark_count = 10
        snap2.version_number = 1
        snapshots_result = MagicMock()
        snapshots_result.scalars.return_value.all.return_value = [snap1, snap2]

        session.execute = AsyncMock(
            side_effect=[
                eng_exists_result,
                shelf_result,
                model_result,
                brightness_result,
                gaps_result,
                gap_sev_result,
                seed_result,
                snapshots_result,
            ]
        )

        result = await get_engagement_lead_dashboard(eng_id, session, user)

        assert result["evidence_coverage_pct"] == 70.0
        assert result["overall_confidence"] == 0.85
        assert result["brightness_distribution"].bright_pct == 60.0
        assert result["brightness_distribution"].dim_pct == 30.0
        assert result["brightness_distribution"].dark_pct == 10.0
        assert result["seed_list_coverage_pct"] == 75.0
        assert result["dark_room_shrink_rate"] == 50.0

    @pytest.mark.asyncio
    async def test_wrong_role_gets_403(self) -> None:
        """Non-lead role gets 403."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        user = _make_mock_user(role=UserRole.ENGAGEMENT_LEAD)
        session = _mock_member_session("sme")

        with pytest.raises(HTTPException) as exc_info:
            await get_engagement_lead_dashboard(eng_id, session, user)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_no_data_returns_zero_kpis(self) -> None:
        """Empty engagement returns zero KPIs."""
        eng_id = uuid.uuid4()
        user = _make_mock_user()
        session = AsyncMock()

        # 1. Engagement existence check
        eng_exists_result = _engagement_exists_result()

        # Shelf: no items
        shelf_row = MagicMock()
        shelf_row.total = 0
        shelf_row.received = 0
        shelf_result = MagicMock()
        shelf_result.one.return_value = shelf_row

        # No model
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = None

        # Brightness: no model (model_id=None triggers internal lookup)
        brightness_model_result = MagicMock()
        brightness_model_result.scalar_one_or_none.return_value = None

        # No gaps
        gaps_result = MagicMock()
        gaps_result.all.return_value = []

        # No seeds
        seed_row = MagicMock()
        seed_row.total = 0
        seed_row.active = 0
        seed_result = MagicMock()
        seed_result.one.return_value = seed_row

        # No snapshots
        snapshots_result = MagicMock()
        snapshots_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(
            side_effect=[
                eng_exists_result,
                shelf_result,
                model_result,
                brightness_model_result,
                gaps_result,
                seed_result,
                snapshots_result,
            ]
        )

        result = await get_engagement_lead_dashboard(eng_id, session, user)

        assert result["evidence_coverage_pct"] == 0.0
        assert result["overall_confidence"] == 0.0
        assert result["seed_list_coverage_pct"] == 0.0
        assert result["dark_room_shrink_rate"] == 0.0


# ============================================================
# Scenario 2: Process Analyst dashboard
# ============================================================


class TestProcessAnalystDashboard:
    """GET /api/v1/dashboard/{id}/analyst returns processing status."""

    @pytest.mark.asyncio
    async def test_returns_processing_status_and_conflicts(self) -> None:
        """Analyst sees evidence processing status and conflict queue."""
        eng_id = uuid.uuid4()
        user = _make_mock_user()
        session = AsyncMock()

        # 1. Engagement existence check
        eng_exists_result = _engagement_exists_result()

        # Evidence status counts
        pending_row = MagicMock()
        pending_row.validation_status = "pending"
        pending_row.cnt = 5
        active_row = MagicMock()
        active_row.validation_status = "active"
        active_row.cnt = 15
        status_result = MagicMock()
        status_result.all.return_value = [pending_row, active_row]

        # Latest model id for mapping progress
        model_id_result = MagicMock()
        model_id_result.scalar_one_or_none.return_value = uuid.uuid4()

        # Total elements
        total_elem_result = MagicMock()
        total_elem_result.scalar.return_value = 10

        # Mapped elements (evidence_count > 0)
        mapped_elem_result = MagicMock()
        mapped_elem_result.scalar.return_value = 7

        # Unresolved conflicts (capped at 50)
        conflict1 = MagicMock()
        conflict1.id = uuid.uuid4()
        conflict1.mismatch_type = "sequence_mismatch"
        conflict1.severity = 0.8
        conflict1.resolution_status = "unresolved"
        conflict1.created_at = None
        conflict_result = MagicMock()
        conflict_result.scalars.return_value.all.return_value = [conflict1]

        # Total conflicts count
        total_count_result = MagicMock()
        total_count_result.scalar.return_value = 5

        # Unresolved conflicts count (separate query)
        unresolved_count_result = MagicMock()
        unresolved_count_result.scalar.return_value = 3

        session.execute = AsyncMock(
            side_effect=[
                eng_exists_result,
                status_result,
                model_id_result,
                total_elem_result,
                mapped_elem_result,
                conflict_result,
                total_count_result,
                unresolved_count_result,
            ]
        )

        result = await get_analyst_dashboard(eng_id, session, user)

        assert result["processing_status"].pending == 5
        assert result["processing_status"].active == 15
        assert result["relationship_mapping_pct"] == 70.0
        assert result["unresolved_conflicts"] == 3
        assert result["total_conflicts"] == 5
        assert len(result["conflict_queue"]) == 1

    @pytest.mark.asyncio
    async def test_wrong_role_gets_403(self) -> None:
        """Non-analyst role gets 403."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        user = _make_mock_user(role=UserRole.ENGAGEMENT_LEAD)
        session = _mock_member_session("client")

        with pytest.raises(HTTPException) as exc_info:
            await get_analyst_dashboard(eng_id, session, user)

        assert exc_info.value.status_code == 403


# ============================================================
# Scenario 3: Client Stakeholder read-only view
# ============================================================


class TestClientStakeholderDashboard:
    """GET /api/v1/dashboard/{id}/client returns read-only findings."""

    @pytest.mark.asyncio
    async def test_returns_findings_without_internal_scores(self) -> None:
        """Client sees gap findings without severity scores."""
        eng_id = uuid.uuid4()
        user = _make_mock_user()
        session = AsyncMock()

        # 1. Engagement existence check
        eng_exists_result = _engagement_exists_result()

        # Latest model
        latest_model = MagicMock()
        latest_model.id = uuid.uuid4()
        latest_model.confidence_score = 0.72
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = latest_model

        # Brightness counts (model_id passed directly, no extra lookup)
        brightness_result = MagicMock()
        brightness_result.all.return_value = []

        # Gap findings
        gap1 = MagicMock()
        gap1.id = uuid.uuid4()
        gap1.gap_type = "full_gap"
        gap1.dimension = "process_architecture"
        gap1.recommendation = "Redesign process flow"
        gap1.created_at = None
        gap2 = MagicMock()
        gap2.id = uuid.uuid4()
        gap2.gap_type = "partial_gap"
        gap2.dimension = "technology_and_data"
        gap2.recommendation = None
        gap2.created_at = None
        gaps_result = MagicMock()
        gaps_result.scalars.return_value.all.return_value = [gap1, gap2]

        session.execute = AsyncMock(side_effect=[eng_exists_result, model_result, brightness_result, gaps_result])

        result = await get_client_dashboard(eng_id, session, user)

        assert result["overall_confidence"] == 0.72
        assert len(result["gap_findings"]) == 2
        assert result["total_recommendations"] == 1

        # Verify GapFindingSummary schema excludes severity field
        finding = result["gap_findings"][0]
        assert isinstance(finding, GapFindingSummary)
        assert "severity" not in finding.model_fields

    @pytest.mark.asyncio
    async def test_wrong_role_gets_403(self) -> None:
        """Non-client role gets 403."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        user = _make_mock_user(role=UserRole.ENGAGEMENT_LEAD)
        session = _mock_member_session("engagement_lead")

        with pytest.raises(HTTPException) as exc_info:
            await get_client_dashboard(eng_id, session, user)

        assert exc_info.value.status_code == 403


# ============================================================
# Scenario 4: SME dashboard with review queue
# ============================================================


class TestSmeDashboard:
    """GET /api/v1/dashboard/{id}/sme returns review items."""

    @pytest.mark.asyncio
    async def test_returns_review_stats_and_history(self) -> None:
        """SME sees pending reviews, annotations, and history."""
        eng_id = uuid.uuid4()
        user_id = uuid.uuid4()
        user = _make_mock_user(user_id=user_id)
        session = AsyncMock()

        # 1. Engagement existence check
        eng_exists_result = _engagement_exists_result()

        # Total annotations
        total_result = MagicMock()
        total_result.scalar.return_value = 12

        # Deferred (pending) reviews
        defer_result = MagicMock()
        defer_result.scalar.return_value = 3

        # Confirm count
        confirm_result = MagicMock()
        confirm_result.scalar.return_value = 8

        # Decision history
        decision1 = MagicMock()
        decision1.id = uuid.uuid4()
        decision1.action = "confirm"
        decision1.decision_at = None
        decision2 = MagicMock()
        decision2.id = uuid.uuid4()
        decision2.action = "reject"
        decision2.decision_at = None
        history_result = MagicMock()
        history_result.scalars.return_value.all.return_value = [decision1, decision2]

        session.execute = AsyncMock(
            side_effect=[
                eng_exists_result,
                total_result,
                defer_result,
                confirm_result,
                history_result,
            ]
        )

        result = await get_sme_dashboard(eng_id, session, user)

        assert result["pending_review_count"] == 3
        assert result["total_annotation_count"] == 12
        assert result["confidence_impact"] == 0.67  # 8/12
        assert len(result["decision_history"]) == 2

    @pytest.mark.asyncio
    async def test_no_annotations_returns_zero_impact(self) -> None:
        """SME with no annotations has zero confidence impact."""
        eng_id = uuid.uuid4()
        user = _make_mock_user()
        session = AsyncMock()

        # 1. Engagement existence check
        eng_exists_result = _engagement_exists_result()

        total_result = MagicMock()
        total_result.scalar.return_value = 0
        defer_result = MagicMock()
        defer_result.scalar.return_value = 0
        confirm_result = MagicMock()
        confirm_result.scalar.return_value = 0
        history_result = MagicMock()
        history_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(
            side_effect=[eng_exists_result, total_result, defer_result, confirm_result, history_result]
        )

        result = await get_sme_dashboard(eng_id, session, user)

        assert result["confidence_impact"] == 0.0
        assert result["total_annotation_count"] == 0

    @pytest.mark.asyncio
    async def test_wrong_role_gets_403(self) -> None:
        """Non-SME role gets 403."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        user = _make_mock_user(role=UserRole.ENGAGEMENT_LEAD)
        session = _mock_member_session("analyst")

        with pytest.raises(HTTPException) as exc_info:
            await get_sme_dashboard(eng_id, session, user)

        assert exc_info.value.status_code == 403


# ============================================================
# Schema validation tests
# ============================================================


class TestPersonaDashboardSchemas:
    """Schema validation for persona dashboard response models."""

    def test_brightness_distribution_validates(self) -> None:
        """BrightnessDistribution schema is valid."""
        entry = BrightnessDistribution(bright_pct=60.0, dim_pct=30.0, dark_pct=10.0, total_elements=10)
        assert entry.bright_pct + entry.dim_pct + entry.dark_pct == 100.0

    def test_tom_alignment_entry_validates(self) -> None:
        """TOMAlignmentEntry schema is valid."""
        entry = TOMAlignmentEntry(dimension="process_architecture", alignment_pct=85.0)
        assert entry.alignment_pct == 85.0

    def test_engagement_lead_dashboard_validates(self) -> None:
        """EngagementLeadDashboard schema is valid."""
        resp = EngagementLeadDashboard(
            engagement_id="eng-1",
            evidence_coverage_pct=70.0,
            overall_confidence=0.85,
            brightness_distribution=BrightnessDistribution(),
            tom_alignment=[],
            gap_counts={"high": 0, "medium": 0, "low": 0},
            seed_list_coverage_pct=75.0,
            dark_room_shrink_rate=10.0,
        )
        assert resp.evidence_coverage_pct == 70.0

    def test_processing_status_counts_validates(self) -> None:
        """ProcessingStatusCounts schema is valid."""
        entry = ProcessingStatusCounts(pending=5, validated=3, active=10)
        assert entry.pending == 5

    def test_conflict_queue_item_validates(self) -> None:
        """ConflictQueueItem schema is valid."""
        entry = ConflictQueueItem(
            id="c-1",
            mismatch_type="sequence_mismatch",
            severity=0.8,
            resolution_status="unresolved",
        )
        assert entry.severity == 0.8

    def test_analyst_dashboard_validates(self) -> None:
        """ProcessAnalystDashboard schema is valid."""
        resp = ProcessAnalystDashboard(
            engagement_id="eng-1",
            processing_status=ProcessingStatusCounts(),
            relationship_mapping_pct=70.0,
            conflict_queue=[],
            total_conflicts=5,
            unresolved_conflicts=2,
        )
        assert resp.relationship_mapping_pct == 70.0

    def test_sme_dashboard_validates(self) -> None:
        """SmeDashboard schema is valid."""
        resp = SmeDashboard(
            engagement_id="eng-1",
            pending_review_count=3,
            total_annotation_count=12,
            confidence_impact=0.67,
            decision_history=[],
        )
        assert resp.confidence_impact == 0.67

    def test_client_dashboard_validates(self) -> None:
        """ClientStakeholderDashboard schema is valid."""
        resp = ClientStakeholderDashboard(
            engagement_id="eng-1",
            overall_confidence=0.72,
            brightness_distribution=BrightnessDistribution(),
            gap_findings=[],
            total_recommendations=0,
        )
        assert resp.total_recommendations == 0

    def test_gap_finding_summary_excludes_severity(self) -> None:
        """GapFindingSummary schema must not expose severity."""
        assert "severity" not in GapFindingSummary.model_fields
        finding = GapFindingSummary(
            id="g-1",
            gap_type="full_gap",
            dimension="process_architecture",
            recommendation="Fix it",
        )
        serialized = finding.model_dump()
        assert "severity" not in serialized
