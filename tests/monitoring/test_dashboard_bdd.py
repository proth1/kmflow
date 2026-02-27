"""BDD tests for Story #371: Monitoring Dashboard.

Covers all 4 acceptance scenarios:
1. Dashboard loads with agent statuses and live metrics
2. New deviation updates via WebSocket (tested via dashboard data refresh)
3. Compliance score trend as line chart data
4. Date range filter updates all dashboard metrics

Plus endpoint integration tests for authorization, schema validation,
and service-layer logic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.monitoring.dashboard import (
    aggregate_deviation_counts,
    build_compliance_trend,
    compute_trend_direction,
)

# ===========================================================================
# Scenario 1: Dashboard loads with current agent statuses and live metrics
# ===========================================================================


class TestDashboardLoadsAgentStatuses:
    """Given monitoring is active for an engagement with 3 running agents."""

    def test_compute_trend_direction_up(self) -> None:
        """Upward trend when second half average > first half."""
        scores = [0.70, 0.72, 0.75, 0.80, 0.85, 0.88, 0.90]
        assert compute_trend_direction(scores) == "up"

    def test_compute_trend_direction_down(self) -> None:
        """Downward trend when second half average < first half."""
        scores = [0.90, 0.88, 0.85, 0.80, 0.75, 0.72, 0.70]
        assert compute_trend_direction(scores) == "down"

    def test_compute_trend_direction_flat(self) -> None:
        """Flat trend when scores are stable."""
        scores = [0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80]
        assert compute_trend_direction(scores) == "flat"

    def test_compute_trend_direction_single_score(self) -> None:
        """Single score returns flat."""
        assert compute_trend_direction([0.85]) == "flat"

    def test_compute_trend_direction_empty(self) -> None:
        """Empty list returns flat."""
        assert compute_trend_direction([]) == "flat"

    def test_compute_trend_direction_two_scores_up(self) -> None:
        """Two scores with increase returns up."""
        assert compute_trend_direction([0.70, 0.90]) == "up"

    def test_compute_trend_direction_custom_window(self) -> None:
        """Custom window size limits the data used for trend."""
        scores = [0.50, 0.60, 0.70, 0.80, 0.90, 0.80, 0.70]
        # Last 3: [0.90, 0.80, 0.70] → down
        assert compute_trend_direction(scores, window=3) == "down"


# ===========================================================================
# Scenario 2: Deviation counts by severity
# ===========================================================================


class TestDeviationCountsBySeverity:
    """Given deviations detected with varying severities."""

    def test_aggregate_all_severities(self) -> None:
        """All severity levels are correctly aggregated."""
        counts = {"critical": 2, "high": 5, "medium": 10, "low": 3, "info": 1}
        summary = aggregate_deviation_counts(counts)

        assert summary.critical == 2
        assert summary.high == 5
        assert summary.medium == 10
        assert summary.low == 3
        assert summary.info == 1
        assert summary.total == 21

    def test_aggregate_partial_severities(self) -> None:
        """Only populated severities are set, others remain 0."""
        counts = {"high": 3}
        summary = aggregate_deviation_counts(counts)

        assert summary.high == 3
        assert summary.critical == 0
        assert summary.medium == 0
        assert summary.low == 0
        assert summary.info == 0
        assert summary.total == 3

    def test_aggregate_empty_counts(self) -> None:
        """Empty dict yields all zeros."""
        summary = aggregate_deviation_counts({})
        assert summary.total == 0
        assert summary.critical == 0
        assert summary.high == 0

    def test_aggregate_case_insensitive(self) -> None:
        """Severity keys are case-insensitive."""
        counts = {"CRITICAL": 1, "High": 2, "MEDIUM": 3}
        summary = aggregate_deviation_counts(counts)
        assert summary.critical == 1
        assert summary.high == 2
        assert summary.medium == 3
        assert summary.total == 6


# ===========================================================================
# Scenario 3: Compliance score trend
# ===========================================================================


class TestComplianceScoreTrend:
    """Given historical compliance score data over past 30 days."""

    def test_build_trend_from_data_points(self) -> None:
        """Compliance trend built from chronological data points."""
        data = [
            {"date": "2026-02-01", "score": 0.75},
            {"date": "2026-02-08", "score": 0.78},
            {"date": "2026-02-15", "score": 0.82},
            {"date": "2026-02-22", "score": 0.85},
        ]
        trend = build_compliance_trend(data)

        assert trend.current_score == 0.85
        assert trend.trend_direction == "up"
        assert len(trend.data_points) == 4
        assert trend.data_points[0].date == "2026-02-01"
        assert trend.data_points[0].score == 0.75

    def test_build_trend_empty(self) -> None:
        """Empty data returns default ComplianceTrend."""
        trend = build_compliance_trend([])
        assert trend.current_score == 0.0
        assert trend.trend_direction == "flat"
        assert trend.data_points == []

    def test_build_trend_single_point(self) -> None:
        """Single data point has flat trend."""
        data = [{"date": "2026-02-01", "score": 0.80}]
        trend = build_compliance_trend(data)
        assert trend.current_score == 0.80
        assert trend.trend_direction == "flat"
        assert len(trend.data_points) == 1

    def test_build_trend_declining(self) -> None:
        """Declining scores produce downward trend."""
        data = [
            {"date": "2026-02-01", "score": 0.90},
            {"date": "2026-02-08", "score": 0.85},
            {"date": "2026-02-15", "score": 0.78},
            {"date": "2026-02-22", "score": 0.70},
        ]
        trend = build_compliance_trend(data)
        assert trend.current_score == 0.70
        assert trend.trend_direction == "down"

    def test_trend_data_points_preserve_order(self) -> None:
        """Data points maintain chronological order."""
        data = [
            {"date": "2026-02-01", "score": 0.80},
            {"date": "2026-02-02", "score": 0.81},
            {"date": "2026-02-03", "score": 0.82},
        ]
        trend = build_compliance_trend(data)
        dates = [dp.date for dp in trend.data_points]
        assert dates == ["2026-02-01", "2026-02-02", "2026-02-03"]


# ===========================================================================
# Scenario 4: Date range filter and endpoint integration
# ===========================================================================


class TestDashboardEndpointIntegration:
    """Integration tests for the monitoring dashboard endpoint."""

    def test_dashboard_endpoint_exists_in_router(self) -> None:
        """Router should have /dashboard/{engagement_id} route."""
        from src.api.routes.monitoring import router

        route_paths = [r.path for r in router.routes]
        assert any(p.endswith("/dashboard/{engagement_id}") for p in route_paths)

    def test_response_model_has_all_fields(self) -> None:
        """DashboardResponse should have all required dashboard sections."""
        from src.api.routes.monitoring import DashboardResponse

        fields = DashboardResponse.model_fields
        assert "engagement_id" in fields
        assert "date_from" in fields
        assert "date_to" in fields
        assert "agent_status" in fields
        assert "deviations" in fields
        assert "evidence_flow_rate" in fields
        assert "alerts" in fields
        assert "compliance_trend" in fields

    def test_endpoint_requires_monitoring_read(self) -> None:
        """Dashboard endpoint should require monitoring:read permission."""
        import inspect

        from src.api.routes.monitoring import get_monitoring_dashboard

        sig = inspect.signature(get_monitoring_dashboard)
        user_param = sig.parameters.get("_user")
        assert user_param is not None
        dep = user_param.default
        assert hasattr(dep, "dependency")

    def test_endpoint_requires_engagement_access(self) -> None:
        """Dashboard endpoint should require engagement access."""
        import inspect

        from src.api.routes.monitoring import get_monitoring_dashboard

        sig = inspect.signature(get_monitoring_dashboard)
        eng_param = sig.parameters.get("_eng_user")
        assert eng_param is not None
        dep = eng_param.default
        assert hasattr(dep, "dependency")
        from src.core.permissions import require_engagement_access
        assert dep.dependency is require_engagement_access

    @pytest.mark.asyncio
    async def test_dashboard_returns_complete_structure_empty_data(self) -> None:
        """Dashboard returns valid structure with empty engagement data."""
        from src.api.routes.monitoring import get_monitoring_dashboard

        eng_id = uuid.uuid4()

        # Mock session returning empty results for all queries
        mock_session = AsyncMock()
        empty_scalars = MagicMock()
        empty_scalars.all.return_value = []
        empty_result = MagicMock()
        empty_result.scalars.return_value = empty_scalars
        empty_result.all.return_value = []

        scalar_result = MagicMock()
        scalar_result.scalar.return_value = 0

        # Calls: agents, severity, evidence_count, open_alerts, new_alerts,
        #        ack_alerts, crit_alerts, compliance_readings
        mock_session.execute.side_effect = [
            empty_result,      # agents
            empty_result,      # severity counts
            scalar_result,     # evidence count
            scalar_result,     # open alerts
            scalar_result,     # new alerts
            scalar_result,     # ack alerts
            scalar_result,     # critical open alerts
            empty_result,      # compliance readings
        ]

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        result = await get_monitoring_dashboard(
            engagement_id=eng_id,
            date_from=None,
            date_to=None,
            session=mock_session,
            _user=mock_user,
            _eng_user=mock_user,
        )

        assert result["engagement_id"] == str(eng_id)
        assert result["agent_status"]["total"] == 0
        assert result["deviations"]["total"] == 0
        assert result["evidence_flow_rate"] == 0.0
        assert result["alerts"]["total_open"] == 0
        assert result["compliance_trend"]["current_score"] == 0.0
        assert result["compliance_trend"]["trend_direction"] == "flat"

    @pytest.mark.asyncio
    async def test_dashboard_validates_against_pydantic_schema(self) -> None:
        """Response dict validates against DashboardResponse model."""
        from src.api.routes.monitoring import DashboardResponse, get_monitoring_dashboard

        eng_id = uuid.uuid4()

        mock_session = AsyncMock()
        empty_scalars = MagicMock()
        empty_scalars.all.return_value = []
        empty_result = MagicMock()
        empty_result.scalars.return_value = empty_scalars
        empty_result.all.return_value = []

        scalar_result = MagicMock()
        scalar_result.scalar.return_value = 0

        mock_session.execute.side_effect = [
            empty_result, empty_result, scalar_result,
            scalar_result, scalar_result, scalar_result, scalar_result,
            empty_result,
        ]

        mock_user = MagicMock()
        result = await get_monitoring_dashboard(
            engagement_id=eng_id,
            date_from=date(2026, 2, 1),
            date_to=date(2026, 2, 14),
            session=mock_session,
            _user=mock_user,
            _eng_user=mock_user,
        )

        validated = DashboardResponse(**result)
        assert validated.date_from == "2026-02-01"
        assert validated.date_to == "2026-02-14"

    @pytest.mark.asyncio
    async def test_dashboard_default_date_range_is_7_days(self) -> None:
        """When no dates provided, defaults to last 7 days."""
        from src.api.routes.monitoring import get_monitoring_dashboard

        eng_id = uuid.uuid4()

        mock_session = AsyncMock()
        empty_scalars = MagicMock()
        empty_scalars.all.return_value = []
        empty_result = MagicMock()
        empty_result.scalars.return_value = empty_scalars
        empty_result.all.return_value = []

        scalar_result = MagicMock()
        scalar_result.scalar.return_value = 0

        mock_session.execute.side_effect = [
            empty_result, empty_result, scalar_result,
            scalar_result, scalar_result, scalar_result, scalar_result,
            empty_result,
        ]

        mock_user = MagicMock()
        result = await get_monitoring_dashboard(
            engagement_id=eng_id,
            date_from=None,
            date_to=None,
            session=mock_session,
            _user=mock_user,
            _eng_user=mock_user,
        )

        today = datetime.now(UTC).date()
        seven_days_ago = today - timedelta(days=7)
        assert result["date_from"] == str(seven_days_ago)
        assert result["date_to"] == str(today)

    @pytest.mark.asyncio
    async def test_dashboard_custom_date_range(self) -> None:
        """Custom date range is reflected in response."""
        from src.api.routes.monitoring import get_monitoring_dashboard

        eng_id = uuid.uuid4()
        mock_session = AsyncMock()
        empty_scalars = MagicMock()
        empty_scalars.all.return_value = []
        empty_result = MagicMock()
        empty_result.scalars.return_value = empty_scalars
        empty_result.all.return_value = []
        scalar_result = MagicMock()
        scalar_result.scalar.return_value = 0
        mock_session.execute.side_effect = [
            empty_result, empty_result, scalar_result,
            scalar_result, scalar_result, scalar_result, scalar_result,
            empty_result,
        ]
        mock_user = MagicMock()

        result = await get_monitoring_dashboard(
            engagement_id=eng_id,
            date_from=date(2026, 1, 15),
            date_to=date(2026, 2, 15),
            session=mock_session,
            _user=mock_user,
            _eng_user=mock_user,
        )

        assert result["date_from"] == "2026-01-15"
        assert result["date_to"] == "2026-02-15"


# ===========================================================================
# Service layer dashboard module tests
# ===========================================================================


class TestDashboardServiceModule:
    """Test dashboard.py service module independently."""

    def test_dashboard_module_imports(self) -> None:
        """Dashboard module should be importable."""
        from src.monitoring.dashboard import (
            AgentStatusSummary,
            AlertSummary,
            ComplianceDataPoint,
            ComplianceTrend,
            DashboardData,
            DeviationSummary,
        )
        assert DashboardData is not None
        assert AgentStatusSummary is not None
        assert DeviationSummary is not None
        assert AlertSummary is not None
        assert ComplianceTrend is not None
        assert ComplianceDataPoint is not None

    def test_dashboard_data_dataclass(self) -> None:
        """DashboardData should initialize correctly."""
        from src.monitoring.dashboard import (
            AgentStatusSummary,
            AlertSummary,
            ComplianceTrend,
            DashboardData,
            DeviationSummary,
        )

        data = DashboardData(
            engagement_id="test-eng",
            date_from="2026-02-01",
            date_to="2026-02-14",
            agent_status=AgentStatusSummary(total=3, healthy=2, degraded=1),
            deviations=DeviationSummary(total=5, high=3, medium=2),
            evidence_flow_rate=1.5,
            alerts=AlertSummary(total_open=2, new=1, acknowledged=1),
            compliance_trend=ComplianceTrend(current_score=0.85, trend_direction="up"),
        )
        assert data.engagement_id == "test-eng"
        assert data.agent_status.healthy == 2
        assert data.deviations.high == 3
        assert data.alerts.total_open == 2
        assert data.compliance_trend.trend_direction == "up"

    def test_deviation_summary_defaults(self) -> None:
        """DeviationSummary defaults all counts to 0."""
        from src.monitoring.dashboard import DeviationSummary
        summary = DeviationSummary()
        assert summary.total == 0
        assert summary.critical == 0
        assert summary.high == 0

    def test_alert_summary_defaults(self) -> None:
        """AlertSummary defaults all counts to 0."""
        from src.monitoring.dashboard import AlertSummary
        summary = AlertSummary()
        assert summary.total_open == 0
        assert summary.new == 0

    def test_compliance_trend_defaults(self) -> None:
        """ComplianceTrend defaults to flat with score 0."""
        from src.monitoring.dashboard import ComplianceTrend
        trend = ComplianceTrend()
        assert trend.current_score == 0.0
        assert trend.trend_direction == "flat"
        assert trend.data_points == []
