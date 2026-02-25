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
