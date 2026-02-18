"""Tests for monitoring job and baseline management routes.

Tests the /api/v1/monitoring endpoints for monitoring jobs, baselines,
deviations, alerts, and stats.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.models import (
    MonitoringJob,
    MonitoringSourceType,
    MonitoringStatus,
    ProcessBaseline,
)


class TestMonitoringJobRoutes:
    """Tests for monitoring job lifecycle routes."""

    @pytest.mark.asyncio
    async def test_create_monitoring_job(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test creating a monitoring job with valid data."""
        engagement_id = uuid.uuid4()
        job_id = uuid.uuid4()

        def refresh_side_effect(obj: Any) -> None:
            if isinstance(obj, MonitoringJob):
                obj.id = job_id

        mock_db_session.refresh.side_effect = refresh_side_effect

        response = await client.post(
            "/api/v1/monitoring/jobs",
            json={
                "engagement_id": str(engagement_id),
                "name": "Test Job",
                "source_type": "event_log",
                "schedule_cron": "0 0 * * *",
                "config": {"log_source": "/var/log/app.log"},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Job"
        assert data["status"] == "configuring"
        assert data["source_type"] == "event_log"

    @pytest.mark.asyncio
    async def test_create_monitoring_job_invalid_cron(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test creating a monitoring job with invalid cron expression."""
        engagement_id = uuid.uuid4()
        response = await client.post(
            "/api/v1/monitoring/jobs",
            json={
                "engagement_id": str(engagement_id),
                "name": "Test Job",
                "source_type": "event_log",
                "schedule_cron": "invalid cron",
                "config": {"log_source": "/var/log/app.log"},
            },
        )
        assert response.status_code == 400
        assert "cron" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_monitoring_job_missing_config(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test creating a monitoring job with missing required config."""
        engagement_id = uuid.uuid4()
        response = await client.post(
            "/api/v1/monitoring/jobs",
            json={
                "engagement_id": str(engagement_id),
                "name": "Test Job",
                "source_type": "event_log",
                "schedule_cron": "0 0 * * *",
                "config": {},
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_monitoring_jobs(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test listing all monitoring jobs."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = await client.get("/api/v1/monitoring/jobs")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_list_monitoring_jobs_filter_by_engagement(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test filtering monitoring jobs by engagement_id."""
        engagement_id = uuid.uuid4()
        job_id = uuid.uuid4()

        mock_job = MagicMock(spec=MonitoringJob)
        mock_job.id = job_id
        mock_job.engagement_id = engagement_id
        mock_job.name = "Test Job"
        mock_job.source_type = MonitoringSourceType.EVENT_LOG
        mock_job.status = MonitoringStatus.CONFIGURING
        mock_job.connection_id = None
        mock_job.baseline_id = None
        mock_job.schedule_cron = "0 0 * * *"
        mock_job.config_json = {}
        mock_job.last_run_at = None
        mock_job.next_run_at = None
        mock_job.error_message = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_job]
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/monitoring/jobs?engagement_id={engagement_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_get_monitoring_job(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test getting a monitoring job by ID."""
        job_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        mock_job = MagicMock(spec=MonitoringJob)
        mock_job.id = job_id
        mock_job.engagement_id = engagement_id
        mock_job.name = "Test Job"
        mock_job.source_type = MonitoringSourceType.EVENT_LOG
        mock_job.status = MonitoringStatus.ACTIVE
        mock_job.connection_id = None
        mock_job.baseline_id = None
        mock_job.schedule_cron = "0 0 * * *"
        mock_job.config_json = {}
        mock_job.last_run_at = None
        mock_job.next_run_at = None
        mock_job.error_message = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/monitoring/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(job_id)

    @pytest.mark.asyncio
    async def test_get_monitoring_job_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test getting a monitoring job that does not exist."""
        job_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/monitoring/jobs/{job_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_monitoring_job(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test updating a monitoring job's name."""
        job_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        mock_job = MagicMock(spec=MonitoringJob)
        mock_job.id = job_id
        mock_job.engagement_id = engagement_id
        mock_job.name = "Old Name"
        mock_job.source_type = MonitoringSourceType.EVENT_LOG
        mock_job.status = MonitoringStatus.ACTIVE
        mock_job.connection_id = None
        mock_job.baseline_id = None
        mock_job.schedule_cron = "0 0 * * *"
        mock_job.config_json = {}
        mock_job.last_run_at = None
        mock_job.next_run_at = None
        mock_job.error_message = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_db_session.execute.return_value = mock_result

        response = await client.patch(
            f"/api/v1/monitoring/jobs/{job_id}",
            json={"name": "New Name"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_activate_monitoring_job(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test activating a monitoring job."""
        job_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        mock_job = MagicMock(spec=MonitoringJob)
        mock_job.id = job_id
        mock_job.engagement_id = engagement_id
        mock_job.name = "Test Job"
        mock_job.source_type = MonitoringSourceType.EVENT_LOG
        mock_job.status = MonitoringStatus.CONFIGURING
        mock_job.connection_id = None
        mock_job.baseline_id = None
        mock_job.schedule_cron = "0 0 * * *"
        mock_job.config_json = {}
        mock_job.last_run_at = None
        mock_job.next_run_at = None
        mock_job.error_message = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_db_session.execute.return_value = mock_result

        response = await client.post(f"/api/v1/monitoring/jobs/{job_id}/activate")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_pause_monitoring_job(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test pausing a monitoring job."""
        job_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        mock_job = MagicMock(spec=MonitoringJob)
        mock_job.id = job_id
        mock_job.engagement_id = engagement_id
        mock_job.name = "Test Job"
        mock_job.source_type = MonitoringSourceType.EVENT_LOG
        mock_job.status = MonitoringStatus.ACTIVE
        mock_job.connection_id = None
        mock_job.baseline_id = None
        mock_job.schedule_cron = "0 0 * * *"
        mock_job.config_json = {}
        mock_job.last_run_at = None
        mock_job.next_run_at = None
        mock_job.error_message = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_db_session.execute.return_value = mock_result

        response = await client.post(f"/api/v1/monitoring/jobs/{job_id}/pause")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paused"

    @pytest.mark.asyncio
    async def test_stop_monitoring_job(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test stopping a monitoring job."""
        job_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        mock_job = MagicMock(spec=MonitoringJob)
        mock_job.id = job_id
        mock_job.engagement_id = engagement_id
        mock_job.name = "Test Job"
        mock_job.source_type = MonitoringSourceType.EVENT_LOG
        mock_job.status = MonitoringStatus.ACTIVE
        mock_job.connection_id = None
        mock_job.baseline_id = None
        mock_job.schedule_cron = "0 0 * * *"
        mock_job.config_json = {}
        mock_job.last_run_at = None
        mock_job.next_run_at = None
        mock_job.error_message = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_db_session.execute.return_value = mock_result

        response = await client.post(f"/api/v1/monitoring/jobs/{job_id}/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"


class TestBaselineRoutes:
    """Tests for process baseline routes."""

    @pytest.mark.asyncio
    async def test_create_baseline(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test creating a process baseline."""
        engagement_id = uuid.uuid4()
        baseline_id = uuid.uuid4()

        def refresh_side_effect(obj: Any) -> None:
            if isinstance(obj, ProcessBaseline):
                obj.id = baseline_id
                obj.created_at = datetime.now(UTC)

        mock_db_session.refresh.side_effect = refresh_side_effect

        response = await client.post(
            "/api/v1/monitoring/baselines",
            json={
                "engagement_id": str(engagement_id),
                "name": "Test Baseline",
                "snapshot_data": {"elements": []},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Baseline"

    @pytest.mark.asyncio
    async def test_list_baselines(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test listing process baselines."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = await client.get("/api/v1/monitoring/baselines")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_baseline(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test getting a baseline by ID."""
        baseline_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        mock_baseline = MagicMock(spec=ProcessBaseline)
        mock_baseline.id = baseline_id
        mock_baseline.engagement_id = engagement_id
        mock_baseline.process_model_id = None
        mock_baseline.name = "Test Baseline"
        mock_baseline.element_count = 0
        mock_baseline.process_hash = None
        mock_baseline.is_active = True
        mock_baseline.created_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_baseline
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/monitoring/baselines/{baseline_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(baseline_id)

    @pytest.mark.asyncio
    async def test_get_baseline_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test getting a baseline that does not exist."""
        baseline_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/monitoring/baselines/{baseline_id}")
        assert response.status_code == 404


class TestDeviationRoutes:
    """Tests for process deviation routes."""

    @pytest.mark.asyncio
    async def test_list_deviations(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test listing process deviations."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = await client.get("/api/v1/monitoring/deviations")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_deviation_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test getting a deviation that does not exist."""
        deviation_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/monitoring/deviations/{deviation_id}")
        assert response.status_code == 404


class TestAlertRoutes:
    """Tests for monitoring alert routes."""

    @pytest.mark.asyncio
    async def test_list_alerts(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test listing monitoring alerts."""
        mock_scalars_result = MagicMock()
        mock_scalars_result.all.return_value = []

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        # First execute for the query, second for the count
        mock_db_session.execute.side_effect = [
            MagicMock(scalars=MagicMock(return_value=mock_scalars_result)),
            mock_count_result,
        ]

        response = await client.get("/api/v1/monitoring/alerts")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_alert_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test getting an alert that does not exist."""
        alert_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/monitoring/alerts/{alert_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_alert_action_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test performing an action on an alert that does not exist."""
        alert_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.post(
            f"/api/v1/monitoring/alerts/{alert_id}/action",
            json={"action": "acknowledge", "actor": "test_user"},
        )
        assert response.status_code == 404


class TestMonitoringStats:
    """Tests for monitoring statistics route."""

    @pytest.mark.asyncio
    async def test_get_monitoring_stats(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Test getting monitoring stats for an engagement."""
        engagement_id = uuid.uuid4()

        # Mock all count queries
        mock_db_session.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=2)),  # active_jobs
            MagicMock(scalar=MagicMock(return_value=5)),  # total_deviations
            MagicMock(scalar=MagicMock(return_value=3)),  # open_alerts
            MagicMock(scalar=MagicMock(return_value=1)),  # critical_alerts
        ]

        response = await client.get(f"/api/v1/monitoring/stats/{engagement_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["active_jobs"] == 2
        assert data["total_deviations"] == 5
        assert data["open_alerts"] == 3
        assert data["critical_alerts"] == 1
