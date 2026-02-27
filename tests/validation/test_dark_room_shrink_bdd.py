"""BDD tests for Story #370: Dark-Room Shrink Rate Tracking Dashboard.

Covers all 3 acceptance scenarios:
1. Per-version shrink rate computation
2. Below-target alert generation
3. Illumination timeline

Plus endpoint integration tests for authorization and response shape.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.validation.dark_room import (
    DEFAULT_SHRINK_RATE_TARGET,
    IlluminationEvent,
    ShrinkRateAlert,
    VersionShrinkData,
    compute_illumination_timeline,
    compute_shrink_rates,
    generate_alerts,
)

# ===========================================================================
# Scenario 1: Per-Version Shrink Rate Computation
# ===========================================================================


class TestShrinkRateComputation:
    """Given 3 POV versions with Dark segment counts of 20, 16, and 12."""

    def _make_snapshots(
        self, dark_counts: list[int], dim_counts: list[int] | None = None, bright_counts: list[int] | None = None
    ) -> list[dict]:
        """Create snapshot dicts for testing."""
        if dim_counts is None:
            dim_counts = [0] * len(dark_counts)
        if bright_counts is None:
            bright_counts = [0] * len(dark_counts)
        snapshots = []
        for i, (d, dim, b) in enumerate(zip(dark_counts, dim_counts, bright_counts, strict=True)):
            total = d + dim + b
            snapshots.append({
                "version_number": i + 1,
                "pov_version_id": str(uuid.uuid4()),
                "dark_count": d,
                "dim_count": dim,
                "bright_count": b,
                "total_elements": total,
                "snapshot_at": f"2026-02-{20 + i}T12:00:00Z",
            })
        return snapshots

    def test_three_versions_shrink_rates(self) -> None:
        """v1:20, v2:16, v3:12 → v1→v2: 20%, v2→v3: 25%."""
        snapshots = self._make_snapshots([20, 16, 12])
        versions = compute_shrink_rates(snapshots)

        assert len(versions) == 3
        assert versions[0].dark_count == 20
        assert versions[0].reduction_pct is None  # First version has no predecessor
        assert versions[1].dark_count == 16
        assert versions[1].reduction_pct == pytest.approx(20.0, abs=0.1)
        assert versions[2].dark_count == 12
        assert versions[2].reduction_pct == pytest.approx(25.0, abs=0.1)

    def test_per_version_counts_returned(self) -> None:
        """Per-version Dark segment counts are returned."""
        snapshots = self._make_snapshots([20, 16, 12], [5, 7, 10], [15, 17, 18])
        versions = compute_shrink_rates(snapshots)

        assert versions[0].dim_count == 5
        assert versions[0].bright_count == 15
        assert versions[0].total_elements == 40
        assert versions[2].dim_count == 10
        assert versions[2].bright_count == 18

    def test_single_version_no_reduction(self) -> None:
        """Single version has no reduction percentage."""
        snapshots = self._make_snapshots([20])
        versions = compute_shrink_rates(snapshots)

        assert len(versions) == 1
        assert versions[0].reduction_pct is None

    def test_zero_dark_previous_version(self) -> None:
        """When previous version had 0 dark, reduction is 0%."""
        snapshots = self._make_snapshots([0, 5])
        versions = compute_shrink_rates(snapshots)

        assert versions[1].reduction_pct == 0.0

    def test_empty_snapshots(self) -> None:
        """Empty snapshot list returns empty results."""
        assert compute_shrink_rates([]) == []

    def test_increasing_dark_count_negative_rate(self) -> None:
        """When dark segments increase, reduction is negative."""
        snapshots = self._make_snapshots([10, 15])
        versions = compute_shrink_rates(snapshots)

        assert versions[1].reduction_pct == pytest.approx(-50.0, abs=0.1)

    def test_complete_illumination_100_pct(self) -> None:
        """Going from dark to zero dark = 100% reduction."""
        snapshots = self._make_snapshots([10, 0])
        versions = compute_shrink_rates(snapshots)

        assert versions[1].reduction_pct == pytest.approx(100.0, abs=0.1)

    def test_version_numbers_preserved(self) -> None:
        """Version numbers from snapshots are preserved."""
        snapshots = self._make_snapshots([20, 16])
        versions = compute_shrink_rates(snapshots)

        assert versions[0].version_number == 1
        assert versions[1].version_number == 2


# ===========================================================================
# Scenario 2: Below-Target Alert
# ===========================================================================


class TestBelowTargetAlert:
    """Given a POV version where the Dark segment shrink rate is 8% (below 15% target)."""

    def test_below_target_generates_warning(self) -> None:
        """Alert with severity='warning' is generated when rate < target."""
        versions = [
            VersionShrinkData(
                version_number=1, pov_version_id="pov-1",
                dark_count=20, dim_count=5, bright_count=15, total_elements=40,
            ),
            VersionShrinkData(
                version_number=2, pov_version_id="pov-2",
                dark_count=18, dim_count=7, bright_count=15, total_elements=40,
                reduction_pct=10.0,  # 10% < 15% target
            ),
        ]
        alerts = generate_alerts(versions)

        assert len(alerts) == 1
        assert alerts[0].severity == "warning"
        assert alerts[0].version_number == 2
        assert alerts[0].actual_rate == 10.0
        assert alerts[0].target_rate == DEFAULT_SHRINK_RATE_TARGET

    def test_alert_message_recommends_evidence_acquisition(self) -> None:
        """Alert message recommends targeted evidence acquisition."""
        versions = [
            VersionShrinkData(
                version_number=2, pov_version_id="pov-2",
                dark_count=18, dim_count=7, bright_count=15, total_elements=40,
                reduction_pct=8.0,
            ),
        ]
        alerts = generate_alerts(versions)

        assert len(alerts) == 1
        assert "targeted evidence acquisition" in alerts[0].message.lower()

    def test_alert_includes_dark_segments(self) -> None:
        """Alert lists the specific Dark segments contributing to low rate."""
        versions = [
            VersionShrinkData(
                version_number=2, pov_version_id="pov-2",
                dark_count=18, dim_count=7, bright_count=15, total_elements=40,
                reduction_pct=8.0,
            ),
        ]
        dark_names = ["Invoice Processing", "Payment Reconciliation"]
        alerts = generate_alerts(versions, dark_segment_names=dark_names)

        assert alerts[0].dark_segments == dark_names

    def test_above_target_no_alert(self) -> None:
        """No alert when shrink rate is above target."""
        versions = [
            VersionShrinkData(
                version_number=2, pov_version_id="pov-2",
                dark_count=10, dim_count=10, bright_count=20, total_elements=40,
                reduction_pct=20.0,  # Above 15% target
            ),
        ]
        alerts = generate_alerts(versions)
        assert len(alerts) == 0

    def test_exactly_at_target_no_alert(self) -> None:
        """No alert when shrink rate is exactly at the target boundary."""
        versions = [
            VersionShrinkData(
                version_number=2, pov_version_id="pov-2",
                dark_count=17, dim_count=10, bright_count=13, total_elements=40,
                reduction_pct=15.0,  # Exactly at target
            ),
        ]
        alerts = generate_alerts(versions)
        assert len(alerts) == 0

    def test_first_version_no_alert(self) -> None:
        """First version (no reduction_pct) should not trigger an alert."""
        versions = [
            VersionShrinkData(
                version_number=1, pov_version_id="pov-1",
                dark_count=20, dim_count=5, bright_count=15, total_elements=40,
            ),
        ]
        alerts = generate_alerts(versions)
        assert len(alerts) == 0

    def test_custom_target_rate(self) -> None:
        """Custom target rate should be respected."""
        versions = [
            VersionShrinkData(
                version_number=2, pov_version_id="pov-2",
                dark_count=16, dim_count=10, bright_count=14, total_elements=40,
                reduction_pct=20.0,  # Above 15% but below 25%
            ),
        ]
        alerts = generate_alerts(versions, target_rate=25.0)
        assert len(alerts) == 1
        assert alerts[0].target_rate == 25.0

    def test_multiple_versions_below_target(self) -> None:
        """Multiple versions below target each generate an alert."""
        versions = [
            VersionShrinkData(
                version_number=1, pov_version_id="pov-1",
                dark_count=20, dim_count=5, bright_count=15, total_elements=40,
            ),
            VersionShrinkData(
                version_number=2, pov_version_id="pov-2",
                dark_count=19, dim_count=6, bright_count=15, total_elements=40,
                reduction_pct=5.0,
            ),
            VersionShrinkData(
                version_number=3, pov_version_id="pov-3",
                dark_count=18, dim_count=7, bright_count=15, total_elements=40,
                reduction_pct=5.3,
            ),
        ]
        alerts = generate_alerts(versions)
        assert len(alerts) == 2


# ===========================================================================
# Scenario 3: Illumination Timeline
# ===========================================================================


class TestIlluminationTimeline:
    """Given a Dark segment illuminated between v2 and v3."""

    def test_dark_to_dim_illumination(self) -> None:
        """Segment moving from dark to dim creates illumination event."""
        elements = [
            {
                "element_name": "Invoice Processing",
                "element_id": "el-1",
                "brightness_classification": "dark",
                "version_number": 1,
                "pov_version_id": "pov-1",
                "evidence_ids": [],
            },
            {
                "element_name": "Invoice Processing",
                "element_id": "el-2",
                "brightness_classification": "dim",
                "version_number": 2,
                "pov_version_id": "pov-2",
                "evidence_ids": ["ev-1", "ev-2"],
            },
        ]
        events = compute_illumination_timeline(elements)

        assert len(events) == 1
        assert events[0].element_name == "Invoice Processing"
        assert events[0].from_classification == "dark"
        assert events[0].to_classification == "dim"
        assert events[0].illuminated_in_version == 2
        assert events[0].evidence_ids == ["ev-1", "ev-2"]

    def test_dark_to_bright_illumination(self) -> None:
        """Segment jumping from dark to bright creates illumination event."""
        elements = [
            {
                "element_name": "Payment",
                "element_id": "el-1",
                "brightness_classification": "dark",
                "version_number": 1,
                "pov_version_id": "pov-1",
                "evidence_ids": [],
            },
            {
                "element_name": "Payment",
                "element_id": "el-2",
                "brightness_classification": "bright",
                "version_number": 2,
                "pov_version_id": "pov-2",
                "evidence_ids": ["ev-3"],
            },
        ]
        events = compute_illumination_timeline(elements)

        assert len(events) == 1
        assert events[0].to_classification == "bright"

    def test_dim_to_bright_not_illumination(self) -> None:
        """Segment moving from dim to bright is NOT an illumination event (already illuminated)."""
        elements = [
            {
                "element_name": "Review",
                "element_id": "el-1",
                "brightness_classification": "dim",
                "version_number": 1,
                "pov_version_id": "pov-1",
                "evidence_ids": [],
            },
            {
                "element_name": "Review",
                "element_id": "el-2",
                "brightness_classification": "bright",
                "version_number": 2,
                "pov_version_id": "pov-2",
                "evidence_ids": ["ev-4"],
            },
        ]
        events = compute_illumination_timeline(elements)
        assert len(events) == 0

    def test_no_change_no_event(self) -> None:
        """Segment staying dark generates no illumination event."""
        elements = [
            {
                "element_name": "Archive",
                "element_id": "el-1",
                "brightness_classification": "dark",
                "version_number": 1,
                "pov_version_id": "pov-1",
                "evidence_ids": [],
            },
            {
                "element_name": "Archive",
                "element_id": "el-2",
                "brightness_classification": "dark",
                "version_number": 2,
                "pov_version_id": "pov-2",
                "evidence_ids": [],
            },
        ]
        events = compute_illumination_timeline(elements)
        assert len(events) == 0

    def test_multiple_elements_illumination(self) -> None:
        """Multiple elements illuminated across versions."""
        elements = [
            # Element A: dark → dim in v2
            {"element_name": "A", "element_id": "a1", "brightness_classification": "dark", "version_number": 1, "pov_version_id": "pov-1", "evidence_ids": []},
            {"element_name": "A", "element_id": "a2", "brightness_classification": "dim", "version_number": 2, "pov_version_id": "pov-2", "evidence_ids": ["ev-a"]},
            # Element B: dark → dark in v2, dark → bright in v3
            {"element_name": "B", "element_id": "b1", "brightness_classification": "dark", "version_number": 1, "pov_version_id": "pov-1", "evidence_ids": []},
            {"element_name": "B", "element_id": "b2", "brightness_classification": "dark", "version_number": 2, "pov_version_id": "pov-2", "evidence_ids": []},
            {"element_name": "B", "element_id": "b3", "brightness_classification": "bright", "version_number": 3, "pov_version_id": "pov-3", "evidence_ids": ["ev-b1", "ev-b2"]},
        ]
        events = compute_illumination_timeline(elements)

        assert len(events) == 2
        a_event = next(e for e in events if e.element_name == "A")
        b_event = next(e for e in events if e.element_name == "B")

        assert a_event.illuminated_in_version == 2
        assert a_event.to_classification == "dim"

        assert b_event.illuminated_in_version == 3
        assert b_event.to_classification == "bright"
        assert b_event.evidence_ids == ["ev-b1", "ev-b2"]

    def test_evidence_links_in_timeline(self) -> None:
        """Evidence acquisitions that contributed to illumination are linked."""
        elements = [
            {"element_name": "Verify", "element_id": "v1", "brightness_classification": "dark", "version_number": 1, "pov_version_id": "pov-1", "evidence_ids": []},
            {"element_name": "Verify", "element_id": "v2", "brightness_classification": "dim", "version_number": 2, "pov_version_id": "pov-2", "evidence_ids": ["ev-x", "ev-y", "ev-z"]},
        ]
        events = compute_illumination_timeline(elements)

        assert events[0].evidence_ids == ["ev-x", "ev-y", "ev-z"]

    def test_empty_elements_list(self) -> None:
        """Empty elements list returns empty timeline."""
        assert compute_illumination_timeline([]) == []

    def test_none_evidence_ids_handled(self) -> None:
        """None evidence_ids should be handled gracefully."""
        elements = [
            {"element_name": "X", "element_id": "x1", "brightness_classification": "dark", "version_number": 1, "pov_version_id": "pov-1", "evidence_ids": None},
            {"element_name": "X", "element_id": "x2", "brightness_classification": "dim", "version_number": 2, "pov_version_id": "pov-2", "evidence_ids": None},
        ]
        events = compute_illumination_timeline(elements)

        assert len(events) == 1
        assert events[0].evidence_ids == []


# ===========================================================================
# Model and Schema tests
# ===========================================================================


class TestDarkRoomModel:
    """Test DarkRoomSnapshot model structure."""

    def test_model_tablename(self) -> None:
        """Table name should be dark_room_snapshots."""
        from src.core.models.dark_room import DarkRoomSnapshot

        assert DarkRoomSnapshot.__tablename__ == "dark_room_snapshots"

    def test_model_has_required_columns(self) -> None:
        """Model should have all required columns."""
        from src.core.models.dark_room import DarkRoomSnapshot

        columns = {c.name for c in DarkRoomSnapshot.__table__.columns}
        assert "id" in columns
        assert "engagement_id" in columns
        assert "pov_version_id" in columns
        assert "version_number" in columns
        assert "dark_count" in columns
        assert "dim_count" in columns
        assert "bright_count" in columns
        assert "total_elements" in columns
        assert "snapshot_at" in columns

    def test_model_has_indexes(self) -> None:
        """Model should have indexes on engagement_id and pov_version_id."""
        from src.core.models.dark_room import DarkRoomSnapshot

        index_names = {idx.name for idx in DarkRoomSnapshot.__table__.indexes}
        assert "ix_dark_room_snapshots_engagement_id" in index_names
        assert "ix_dark_room_snapshots_pov_version_id" in index_names

    def test_model_exportable_from_init(self) -> None:
        """DarkRoomSnapshot should be importable from src.core.models."""
        from src.core.models import DarkRoomSnapshot

        assert DarkRoomSnapshot.__tablename__ == "dark_room_snapshots"


class TestDashboardEndpointSchema:
    """Test dark-room-shrink endpoint schema."""

    def test_endpoint_exists_in_router(self) -> None:
        """Validation router should have /dark-room-shrink route."""
        from src.api.routes.validation import router

        route_paths = [r.path for r in router.routes]
        assert any(p.endswith("/dark-room-shrink") for p in route_paths)

    def test_response_model_fields(self) -> None:
        """DarkRoomDashboardResponse should have all required fields."""
        from src.api.routes.validation import DarkRoomDashboardResponse

        fields = DarkRoomDashboardResponse.model_fields
        assert "engagement_id" in fields
        assert "shrink_rate_target" in fields
        assert "versions" in fields
        assert "alerts" in fields
        assert "illumination_timeline" in fields


class TestMigration044:
    """Test migration 044 structure."""

    def test_migration_revision(self) -> None:
        """Migration 044 should have correct revision chain."""
        import importlib
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "m044", "alembic/versions/044_dark_room_snapshots.py"
        )
        m044 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m044)

        assert m044.revision == "044"
        assert m044.down_revision == "043"

    def test_migration_has_upgrade_downgrade(self) -> None:
        """Migration should have upgrade and downgrade functions."""
        import importlib
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "m044", "alembic/versions/044_dark_room_snapshots.py"
        )
        m044 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m044)

        assert callable(m044.upgrade)
        assert callable(m044.downgrade)


class TestConstants:
    """Test constants and defaults."""

    def test_default_shrink_rate_target(self) -> None:
        """Default shrink rate target should be 15%."""
        assert DEFAULT_SHRINK_RATE_TARGET == 15.0

    def test_dataclass_defaults(self) -> None:
        """VersionShrinkData should have sensible defaults."""
        v = VersionShrinkData(
            version_number=1,
            pov_version_id="test",
            dark_count=10,
            dim_count=5,
            bright_count=3,
            total_elements=18,
        )
        assert v.reduction_pct is None
        assert v.snapshot_at == ""

    def test_alert_dataclass(self) -> None:
        """ShrinkRateAlert should initialize correctly."""
        alert = ShrinkRateAlert(
            severity="warning",
            message="Test alert",
            version_number=2,
            actual_rate=8.0,
            target_rate=15.0,
        )
        assert alert.dark_segments == []

    def test_illumination_event_dataclass(self) -> None:
        """IlluminationEvent should initialize correctly."""
        event = IlluminationEvent(
            element_name="Test",
            element_id="el-1",
            from_classification="dark",
            to_classification="dim",
            illuminated_in_version=2,
            pov_version_id="pov-2",
        )
        assert event.evidence_ids == []


# ===========================================================================
# Endpoint Integration Tests
# ===========================================================================


class TestDarkRoomEndpointIntegration:
    """Integration tests for the dark-room-shrink endpoint."""

    def test_endpoint_uses_require_engagement_access(self) -> None:
        """Endpoint should use require_engagement_access (not require_permission)."""
        from src.api.routes.validation import get_dark_room_shrink

        # Check the dependency injection params
        params = get_dark_room_shrink.__wrapped__ if hasattr(get_dark_room_shrink, "__wrapped__") else get_dark_room_shrink
        import inspect
        sig = inspect.signature(params)
        current_user_param = sig.parameters.get("current_user")
        assert current_user_param is not None
        # The Depends() default should reference require_engagement_access
        dep = current_user_param.default
        assert hasattr(dep, "dependency")
        from src.core.permissions import require_engagement_access
        assert dep.dependency is require_engagement_access

    def test_endpoint_does_not_use_require_permission(self) -> None:
        """Endpoint should NOT reference require_permission (was CRITICAL review finding)."""
        import inspect

        from src.api.routes.validation import get_dark_room_shrink
        source = inspect.getsource(get_dark_room_shrink)
        assert "require_permission" not in source

    @pytest.mark.asyncio
    async def test_endpoint_returns_correct_structure_with_empty_data(self) -> None:
        """Endpoint returns valid response structure when no snapshots exist."""
        from src.api.routes.validation import get_dark_room_shrink

        eng_id = uuid.uuid4()

        # Mock session that returns empty results
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        result = await get_dark_room_shrink(
            engagement_id=eng_id,
            session=mock_session,
            current_user=mock_user,
        )

        assert result["engagement_id"] == str(eng_id)
        assert result["shrink_rate_target"] == DEFAULT_SHRINK_RATE_TARGET
        assert result["versions"] == []
        assert result["alerts"] == []
        assert result["illumination_timeline"] == []

    @pytest.mark.asyncio
    async def test_endpoint_computes_shrink_rates_from_snapshots(self) -> None:
        """Endpoint correctly fetches and computes shrink rates from DB snapshots."""
        from src.api.routes.validation import get_dark_room_shrink

        eng_id = uuid.uuid4()
        pov_id_1 = uuid.uuid4()
        pov_id_2 = uuid.uuid4()

        # Create mock snapshot objects
        snap1 = MagicMock()
        snap1.version_number = 1
        snap1.pov_version_id = pov_id_1
        snap1.dark_count = 20
        snap1.dim_count = 5
        snap1.bright_count = 15
        snap1.total_elements = 40
        snap1.snapshot_at = MagicMock()
        snap1.snapshot_at.isoformat.return_value = "2026-02-20T12:00:00+00:00"

        snap2 = MagicMock()
        snap2.version_number = 2
        snap2.pov_version_id = pov_id_2
        snap2.dark_count = 16
        snap2.dim_count = 9
        snap2.bright_count = 15
        snap2.total_elements = 40
        snap2.snapshot_at = MagicMock()
        snap2.snapshot_at.isoformat.return_value = "2026-02-21T12:00:00+00:00"

        # Mock session: first execute returns snapshots, second returns dark names, third returns elements
        mock_session = AsyncMock()

        # Snapshot query result
        snap_scalars = MagicMock()
        snap_scalars.all.return_value = [snap1, snap2]
        snap_result = MagicMock()
        snap_result.scalars.return_value = snap_scalars

        # Dark elements query result
        dark_scalars = MagicMock()
        dark_scalars.all.return_value = ["Invoice Processing", "Payment"]
        dark_result = MagicMock()
        dark_result.scalars.return_value = dark_scalars

        # Elements query for illumination timeline
        el_result = MagicMock()
        el_result.all.return_value = []

        mock_session.execute.side_effect = [snap_result, dark_result, el_result]

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        result = await get_dark_room_shrink(
            engagement_id=eng_id,
            session=mock_session,
            current_user=mock_user,
        )

        assert len(result["versions"]) == 2
        assert result["versions"][0]["dark_count"] == 20
        assert result["versions"][0]["reduction_pct"] is None
        assert result["versions"][1]["dark_count"] == 16
        assert result["versions"][1]["reduction_pct"] == pytest.approx(20.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_endpoint_response_matches_pydantic_schema(self) -> None:
        """Response from endpoint should validate against DarkRoomDashboardResponse."""
        from src.api.routes.validation import DarkRoomDashboardResponse, get_dark_room_shrink

        eng_id = uuid.uuid4()

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        result = await get_dark_room_shrink(
            engagement_id=eng_id,
            session=mock_session,
            current_user=mock_user,
        )

        # Validate the dict against the Pydantic model
        validated = DarkRoomDashboardResponse(**result)
        assert validated.engagement_id == str(eng_id)
        assert validated.shrink_rate_target == DEFAULT_SHRINK_RATE_TARGET

    def test_unique_constraint_on_model(self) -> None:
        """Model should have unique constraint on (engagement_id, version_number)."""
        from src.core.models.dark_room import DarkRoomSnapshot

        constraints = DarkRoomSnapshot.__table__.constraints
        uq_names = {c.name for c in constraints if hasattr(c, "columns") and len(c.columns) > 1}
        assert "uq_dark_room_snapshots_engagement_version" in uq_names
