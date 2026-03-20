"""Pydantic schemas for monitoring API routes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.models import MonitoringSourceType, MonitoringStatus

# ---------------------------------------------------------------------------
# Monitoring Job Schemas
# ---------------------------------------------------------------------------


class MonitoringJobCreate(BaseModel):
    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    source_type: MonitoringSourceType
    connection_id: UUID | None = None
    baseline_id: UUID | None = None
    schedule_cron: str = "0 0 * * *"
    config: dict[str, Any] | None = None


class MonitoringJobUpdate(BaseModel):
    name: str | None = None
    schedule_cron: str | None = None
    config: dict[str, Any] | None = None
    status: MonitoringStatus | None = None


class MonitoringJobResponse(BaseModel):
    id: str
    engagement_id: str
    name: str
    source_type: str
    status: str
    connection_id: str | None = None
    baseline_id: str | None = None
    schedule_cron: str
    config: dict[str, Any] | None = None
    last_run_at: str | None = None
    next_run_at: str | None = None
    error_message: str | None = None


class MonitoringJobList(BaseModel):
    items: list[MonitoringJobResponse]
    total: int


# ---------------------------------------------------------------------------
# Baseline Schemas
# ---------------------------------------------------------------------------


class BaselineCreate(BaseModel):
    engagement_id: UUID
    process_model_id: UUID | None = None
    name: str = Field(..., min_length=1, max_length=255)
    snapshot_data: dict[str, Any] | None = None


class BaselineResponse(BaseModel):
    id: str
    engagement_id: str
    process_model_id: str | None = None
    name: str
    element_count: int
    process_hash: str | None = None
    is_active: bool
    created_at: str


class BaselineList(BaseModel):
    items: list[BaselineResponse]
    total: int


# ---------------------------------------------------------------------------
# Deviation Schemas
# ---------------------------------------------------------------------------


class DeviationResponse(BaseModel):
    id: str
    engagement_id: str
    monitoring_job_id: str
    category: str
    description: str
    affected_element: str | None = None
    magnitude: float
    details: dict[str, Any] | None = None
    detected_at: str


class DeviationList(BaseModel):
    items: list[DeviationResponse]
    total: int


# ---------------------------------------------------------------------------
# Alert Schemas
# ---------------------------------------------------------------------------


class AlertResponse(BaseModel):
    id: str
    engagement_id: str
    monitoring_job_id: str
    severity: str
    status: str
    title: str
    description: str
    deviation_ids: list[str] | None = None
    acknowledged_by: str | None = None
    acknowledged_at: str | None = None
    resolved_at: str | None = None
    created_at: str


class AlertList(BaseModel):
    items: list[AlertResponse]
    total: int


class AlertActionRequest(BaseModel):
    action: str = Field(..., pattern="^(acknowledge|resolve|dismiss)$")
    actor: str = "system"


# ---------------------------------------------------------------------------
# Stats Schema
# ---------------------------------------------------------------------------


class MonitoringStats(BaseModel):
    active_jobs: int
    total_deviations: int
    open_alerts: int
    critical_alerts: int


# ---------------------------------------------------------------------------
# Dashboard Schemas (Story #371)
# ---------------------------------------------------------------------------


class AgentStatusResponse(BaseModel):
    """Agent health status summary."""

    total: int
    healthy: int
    degraded: int
    unhealthy: int
    agents: list[dict[str, Any]]


class DeviationCountResponse(BaseModel):
    """Deviation counts by severity."""

    total: int
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0


class AlertSummaryResponse(BaseModel):
    """Alert summary for dashboard."""

    total_open: int
    new: int
    acknowledged: int
    critical_open: int


class ComplianceDataPointResponse(BaseModel):
    """Single compliance score data point."""

    date: str
    score: float


class ComplianceTrendResponse(BaseModel):
    """Compliance score trend for dashboard."""

    current_score: float
    trend_direction: str
    data_points: list[ComplianceDataPointResponse]


class DashboardResponse(BaseModel):
    """Complete monitoring dashboard aggregated data."""

    engagement_id: str
    date_from: str
    date_to: str
    agent_status: AgentStatusResponse
    deviations: DeviationCountResponse
    evidence_flow_rate: float
    alerts: AlertSummaryResponse
    compliance_trend: ComplianceTrendResponse


# ---------------------------------------------------------------------------
# Pipeline Metrics Schema (Story #360)
# ---------------------------------------------------------------------------


class PipelineMetricsResponse(BaseModel):
    """Response from pipeline metrics endpoint."""

    processing_rate: float
    queue_depth: int
    p99_latency_ms: float
    avg_latency_ms: float
    total_processed: int
    total_errors: int
    avg_quality: float
    window_seconds: int


# ---------------------------------------------------------------------------
# Agent Health Schemas (Story #346)
# ---------------------------------------------------------------------------


class AgentHealthEntry(BaseModel):
    """Health status for a single monitoring agent."""

    agent_id: str
    status: str
    last_poll_time: str | None = None
    items_processed_total: int = 0
    consecutive_failures: int = 0
    watermark: str | None = None


class AgentHealthResponse(BaseModel):
    """Response for agent health endpoint."""

    agents: list[AgentHealthEntry]
    total: int
    healthy: int
    degraded: int
    unhealthy: int
