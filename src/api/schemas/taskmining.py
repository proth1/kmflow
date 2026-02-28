"""Pydantic schemas for task mining API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.models.taskmining import (
    ActionCategory,
    AgentStatus,
    CaptureGranularity,
    DeploymentMode,
    DesktopEventType,
    PIIType,
    QuarantineStatus,
    SessionStatus,
)


# ---------------------------------------------------------------------------
# Agent Registration
# ---------------------------------------------------------------------------


class AgentRegisterRequest(BaseModel):
    """Payload for registering a new desktop agent."""

    engagement_id: UUID
    hostname: str = Field(..., min_length=1, max_length=255)
    os_version: str = Field(..., min_length=1, max_length=100)
    agent_version: str = Field(..., min_length=1, max_length=50)
    machine_id: str = Field(..., min_length=1, max_length=255)
    deployment_mode: DeploymentMode
    engagement_end_date: datetime | None = None


class AgentResponse(BaseModel):
    id: str
    engagement_id: str
    hostname: str
    os_version: str
    agent_version: str
    machine_id: str
    status: str
    deployment_mode: str
    capture_granularity: str
    config_json: dict[str, Any] | None = None
    last_heartbeat_at: str | None = None
    engagement_end_date: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    created_at: str


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    total: int


class AgentApproveRequest(BaseModel):
    """Payload for approving/revoking an agent."""

    status: AgentStatus = Field(..., description="Must be 'approved' or 'revoked'")
    capture_granularity: CaptureGranularity | None = None
    config_json: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Event Ingestion
# ---------------------------------------------------------------------------


class EventPayload(BaseModel):
    """A single desktop event from the agent."""

    event_type: DesktopEventType
    timestamp: datetime
    application_name: str | None = None
    window_title: str | None = None
    event_data: dict[str, Any] | None = None
    idempotency_key: str | None = Field(None, max_length=255)


class EventBatchRequest(BaseModel):
    """Batch of events from an agent."""

    agent_id: UUID
    session_id: UUID
    events: list[EventPayload] = Field(..., min_length=1, max_length=1000)


class EventBatchResponse(BaseModel):
    accepted: int
    rejected: int
    duplicates: int
    pii_quarantined: int


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


class HeartbeatRequest(BaseModel):
    agent_id: UUID
    session_id: UUID | None = None
    cpu_percent: float | None = None
    memory_mb: float | None = None
    event_queue_size: int | None = None
    uptime_seconds: int | None = None


class HeartbeatResponse(BaseModel):
    status: str
    server_time: str
    config_updated: bool = False
    config: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Config Pull
# ---------------------------------------------------------------------------


class CaptureConfig(BaseModel):
    """Capture configuration pushed to agents."""

    capture_granularity: str
    app_allowlist: list[str] | None = None
    app_blocklist: list[str] | None = None
    url_domain_only: bool = True
    screenshot_enabled: bool = False
    screenshot_interval_seconds: int = 30
    batch_size: int = 1000
    batch_interval_seconds: int = 30
    idle_timeout_seconds: int = 300
    pii_patterns_version: str = "1.0"


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class SessionResponse(BaseModel):
    id: str
    agent_id: str
    engagement_id: str
    status: str
    started_at: str
    ended_at: str | None = None
    event_count: int
    action_count: int
    pii_detections: int


class SessionListResponse(BaseModel):
    items: list[SessionResponse]
    total: int


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


class ActionResponse(BaseModel):
    id: str
    session_id: str
    engagement_id: str
    category: str
    application_name: str
    window_title: str | None = None
    description: str
    event_count: int
    duration_seconds: float
    started_at: str
    ended_at: str
    action_data: dict[str, Any] | None = None
    evidence_item_id: str | None = None
    created_at: str


class ActionListResponse(BaseModel):
    items: list[ActionResponse]
    total: int


# ---------------------------------------------------------------------------
# PII Quarantine
# ---------------------------------------------------------------------------


class QuarantineItemResponse(BaseModel):
    id: str
    engagement_id: str
    pii_type: str
    pii_field: str
    detection_confidence: float
    status: str
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    auto_delete_at: str
    created_at: str


class QuarantineListResponse(BaseModel):
    items: list[QuarantineItemResponse]
    total: int


class QuarantineActionRequest(BaseModel):
    """Release or delete a quarantined event."""

    action: str = Field(..., description="'release' or 'delete'")


# ---------------------------------------------------------------------------
# Dashboard Stats
# ---------------------------------------------------------------------------


class DashboardStats(BaseModel):
    total_agents: int
    active_agents: int
    total_sessions: int
    active_sessions: int
    total_events: int
    total_actions: int
    total_pii_detections: int
    quarantine_pending: int
    events_last_24h: int
    app_usage: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Visual Context Events (VCE)
# ---------------------------------------------------------------------------


class VCEEventPayload(BaseModel):
    """A single VCE record sent from the agent."""

    engagement_id: UUID
    session_id: UUID | None = None
    agent_id: UUID | None = None
    timestamp: datetime
    screen_state_class: str = Field(..., max_length=50)
    system_guess: str | None = Field(None, max_length=255)
    module_guess: str | None = Field(None, max_length=255)
    confidence: float = Field(..., ge=0.0, le=1.0)
    trigger_reason: str = Field(..., max_length=50)
    sensitivity_flags: list[str] | None = None
    application_name: str = Field(..., min_length=1, max_length=512)
    window_title_redacted: str | None = Field(None, max_length=512)
    dwell_ms: int = Field(..., ge=0)
    interaction_intensity: float | None = None
    snapshot_ref: str | None = Field(None, max_length=1024)
    ocr_text_redacted: str | None = None
    classification_method: str | None = Field(None, max_length=50)


class VCEBatchRequest(BaseModel):
    """Batch of VCE events from an agent."""

    agent_id: UUID
    events: list[VCEEventPayload] = Field(..., min_length=1, max_length=500)


class VCEBatchResponse(BaseModel):
    accepted: int
    rejected: int


class VCEResponse(BaseModel):
    id: str
    engagement_id: str
    session_id: str | None = None
    agent_id: str | None = None
    timestamp: str
    screen_state_class: str
    system_guess: str | None = None
    module_guess: str | None = None
    confidence: float
    trigger_reason: str
    sensitivity_flags: list[str] | None = None
    application_name: str
    window_title_redacted: str | None = None
    dwell_ms: int
    interaction_intensity: float | None = None
    snapshot_ref: str | None = None
    ocr_text_redacted: str | None = None
    classification_method: str | None = None
    created_at: str


class VCEListResponse(BaseModel):
    items: list[VCEResponse]
    total: int


class VCEDistributionEntry(BaseModel):
    screen_state_class: str
    count: int
    percentage: float


class VCEDistributionResponse(BaseModel):
    distributions: list[VCEDistributionEntry]
    total: int


class VCETriggerSummaryEntry(BaseModel):
    trigger_reason: str
    count: int
    avg_confidence: float | None


class VCETriggerSummaryResponse(BaseModel):
    triggers: list[VCETriggerSummaryEntry]


class VCEDwellStatEntry(BaseModel):
    avg: float | None
    median: float | None
    p95: float | None
    count: int | None


class VCEDwellPerAppEntry(VCEDwellStatEntry):
    application_name: str


class VCEDwellPerClassEntry(VCEDwellStatEntry):
    screen_state_class: str


class VCEDwellAnalysisResponse(BaseModel):
    per_app: list[VCEDwellPerAppEntry]
    per_class: list[VCEDwellPerClassEntry]


# ---------------------------------------------------------------------------
# Switching Sequences
# ---------------------------------------------------------------------------


class SwitchingTraceResponse(BaseModel):
    id: str
    engagement_id: str
    session_id: str | None = None
    role_id: str | None = None
    trace_sequence: list[str]
    dwell_durations: list[int]
    total_duration_ms: int
    friction_score: float
    is_ping_pong: bool
    ping_pong_count: int | None = None
    app_count: int
    started_at: str
    ended_at: str
    created_at: str


class SwitchingTraceListResponse(BaseModel):
    items: list[SwitchingTraceResponse]
    total: int


class TransitionMatrixResponse(BaseModel):
    id: str
    engagement_id: str
    role_id: str | None = None
    period_start: str
    period_end: str
    matrix_data: dict[str, Any]
    total_transitions: int
    unique_apps: int
    top_transitions: list[Any] | None = None
    created_at: str


class HighFrictionTraceEntry(BaseModel):
    id: str
    friction_score: float
    app_count: int
    is_ping_pong: bool
    total_duration_ms: int


class PingPongPairEntry(BaseModel):
    pair: str
    trace_count: int


class FrictionAnalysisResponse(BaseModel):
    avg_friction_score: float
    high_friction_traces: list[HighFrictionTraceEntry]
    top_ping_pong_pairs: list[PingPongPairEntry]
    total_traces_analyzed: int


class AssembleSwitchingRequest(BaseModel):
    engagement_id: UUID
    session_id: UUID | None = None


class AssembleSwitchingResponse(BaseModel):
    traces_created: int
    status: str
