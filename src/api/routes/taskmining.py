"""Task mining API routes for desktop agent communication and admin management.

Endpoints:
- POST /agents/register        — Register a new desktop agent
- POST /agents/{id}/approve    — Approve/revoke an agent (admin)
- GET  /agents                 — List agents
- POST /events                 — Batch event ingestion from agents
- GET  /config/{agent_id}      — Pull capture configuration
- POST /heartbeat              — Agent health heartbeat
- GET  /sessions               — List capture sessions
- GET  /actions                — List aggregated actions
- GET  /quarantine             — List PII quarantine items
- POST /quarantine/{id}/action — Release/delete quarantine item
- GET  /dashboard/stats        — Admin dashboard statistics
- GET  /switching/traces       — List switching traces
- GET  /switching/matrix       — Get transition matrix
- GET  /switching/friction     — Get friction analysis summary
- POST /switching/assemble     — Trigger trace assembly
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.schemas.taskmining import (
    ActionListResponse,
    AgentApproveRequest,
    AgentListResponse,
    AgentRegisterRequest,
    AgentResponse,
    AssembleSwitchingRequest,
    AssembleSwitchingResponse,
    CaptureConfig,
    DashboardStats,
    EventBatchRequest,
    EventBatchResponse,
    FrictionAnalysisResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    QuarantineActionRequest,
    QuarantineItemResponse,
    QuarantineListResponse,
    SessionListResponse,
    SwitchingTraceListResponse,
    TransitionMatrixResponse,
    VCEBatchRequest,
    VCEBatchResponse,
    VCEDistributionResponse,
    VCEDwellAnalysisResponse,
    VCEListResponse,
    VCEResponse,
    VCETriggerSummaryResponse,
)
from src.core.models import User
from src.core.models.taskmining import (
    AgentStatus,
    PIIQuarantine,
    QuarantineStatus,
    ScreenStateClass,
    SessionStatus,
    SwitchingTrace,
    TaskMiningAction,
    TaskMiningAgent,
    TaskMiningEvent,
    TaskMiningSession,
    TransitionMatrix,
    VCETriggerReason,
    VisualContextEvent,
)
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/taskmining", tags=["taskmining"])


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _agent_to_response(agent: TaskMiningAgent) -> dict[str, Any]:
    return {
        "id": str(agent.id),
        "engagement_id": str(agent.engagement_id),
        "hostname": agent.hostname,
        "os_version": agent.os_version,
        "agent_version": agent.agent_version,
        "machine_id": agent.machine_id,
        "status": agent.status.value,
        "deployment_mode": agent.deployment_mode.value,
        "capture_granularity": agent.capture_granularity.value,
        "config_json": agent.config_json,
        "last_heartbeat_at": agent.last_heartbeat_at.isoformat() if agent.last_heartbeat_at else None,
        "engagement_end_date": agent.engagement_end_date.isoformat() if agent.engagement_end_date else None,
        "approved_by": agent.approved_by,
        "approved_at": agent.approved_at.isoformat() if agent.approved_at else None,
        "created_at": agent.created_at.isoformat(),
    }


def _session_to_response(s: TaskMiningSession) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "agent_id": str(s.agent_id),
        "engagement_id": str(s.engagement_id),
        "status": s.status.value,
        "started_at": s.started_at.isoformat(),
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        "event_count": s.event_count,
        "action_count": s.action_count,
        "pii_detections": s.pii_detections,
    }


def _action_to_response(a: TaskMiningAction) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "session_id": str(a.session_id),
        "engagement_id": str(a.engagement_id),
        "category": a.category.value,
        "application_name": a.application_name,
        "window_title": a.window_title,
        "description": a.description,
        "event_count": a.event_count,
        "duration_seconds": a.duration_seconds,
        "started_at": a.started_at.isoformat(),
        "ended_at": a.ended_at.isoformat(),
        "action_data": a.action_data,
        "evidence_item_id": str(a.evidence_item_id) if a.evidence_item_id else None,
        "created_at": a.created_at.isoformat(),
    }


def _quarantine_to_response(q: PIIQuarantine) -> dict[str, Any]:
    return {
        "id": str(q.id),
        "engagement_id": str(q.engagement_id),
        "pii_type": q.pii_type.value,
        "pii_field": q.pii_field,
        "detection_confidence": q.detection_confidence,
        "status": q.status.value,
        "reviewed_by": q.reviewed_by,
        "reviewed_at": q.reviewed_at.isoformat() if q.reviewed_at else None,
        "auto_delete_at": q.auto_delete_at.isoformat(),
        "created_at": q.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# POST /agents/register
# ---------------------------------------------------------------------------


@router.post("/agents/register", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def register_agent(
    payload: AgentRegisterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:write")),
) -> dict[str, Any]:
    """Register a new desktop agent.

    The agent starts in PENDING_APPROVAL status and must be approved
    by an admin before it can submit events.
    """
    # Check for duplicate machine_id
    existing = await session.execute(
        select(TaskMiningAgent).where(TaskMiningAgent.machine_id == payload.machine_id).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent with machine_id '{payload.machine_id}' already registered",
        )

    agent = TaskMiningAgent(
        engagement_id=payload.engagement_id,
        hostname=payload.hostname,
        os_version=payload.os_version,
        agent_version=payload.agent_version,
        machine_id=payload.machine_id,
        deployment_mode=payload.deployment_mode,
        engagement_end_date=payload.engagement_end_date,
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)

    logger.info("Agent registered: %s (hostname=%s)", agent.id, agent.hostname)
    return _agent_to_response(agent)


# ---------------------------------------------------------------------------
# POST /agents/{agent_id}/approve
# ---------------------------------------------------------------------------


@router.post("/agents/{agent_id}/approve", response_model=AgentResponse)
async def approve_agent(
    agent_id: UUID,
    payload: AgentApproveRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:admin")),
) -> dict[str, Any]:
    """Approve or revoke a desktop agent (admin operation)."""
    if payload.status not in (AgentStatus.APPROVED, AgentStatus.REVOKED):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Status must be 'approved' or 'revoked'",
        )

    result = await session.execute(select(TaskMiningAgent).where(TaskMiningAgent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    now = datetime.now(UTC)
    agent.status = payload.status
    if payload.status == AgentStatus.APPROVED:
        agent.approved_at = now
        agent.approved_by = current_user.email
        if payload.capture_granularity:
            agent.capture_granularity = payload.capture_granularity
        if payload.config_json:
            agent.config_json = payload.config_json
    elif payload.status == AgentStatus.REVOKED:
        agent.revoked_at = now

    await session.commit()
    await session.refresh(agent)

    logger.info("Agent %s status changed to %s", agent_id, payload.status)
    return _agent_to_response(agent)


# ---------------------------------------------------------------------------
# GET /agents
# ---------------------------------------------------------------------------


@router.get("/agents", response_model=AgentListResponse)
async def list_agents(
    engagement_id: UUID | None = None,
    status_filter: AgentStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:read")),
) -> dict[str, Any]:
    """List registered agents with optional filters."""
    query = select(TaskMiningAgent)
    count_query = select(func.count(TaskMiningAgent.id))

    if engagement_id:
        query = query.where(TaskMiningAgent.engagement_id == engagement_id)
        count_query = count_query.where(TaskMiningAgent.engagement_id == engagement_id)
    if status_filter:
        query = query.where(TaskMiningAgent.status == status_filter)
        count_query = count_query.where(TaskMiningAgent.status == status_filter)

    query = query.order_by(TaskMiningAgent.created_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    agents = [_agent_to_response(a) for a in result.scalars().all()]

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    return {"items": agents, "total": total}


# ---------------------------------------------------------------------------
# POST /events
# ---------------------------------------------------------------------------


@router.post("/events", response_model=EventBatchResponse)
async def ingest_events(
    payload: EventBatchRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:write")),
) -> dict[str, Any]:
    """Ingest a batch of desktop events from an agent.

    Events are validated, PII-filtered (Layer 3), and persisted.
    High-confidence PII events are quarantined.
    """
    # Verify agent exists and is active
    result = await session.execute(select(TaskMiningAgent).where(TaskMiningAgent.id == payload.agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if agent.status not in (AgentStatus.APPROVED, AgentStatus.ACTIVE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent is not active (status={agent.status})",
        )

    # Check engagement end date for engagement-mode agents
    if agent.engagement_end_date and datetime.now(UTC) > agent.engagement_end_date:
        agent.status = AgentStatus.EXPIRED
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent engagement period has expired",
        )

    # Mark agent as active on first event submission
    if agent.status == AgentStatus.APPROVED:
        agent.status = AgentStatus.ACTIVE

    # Verify session exists
    sess_result = await session.execute(select(TaskMiningSession).where(TaskMiningSession.id == payload.session_id))
    mining_session = sess_result.scalar_one_or_none()
    if mining_session is None:
        # Auto-create session if it doesn't exist
        mining_session = TaskMiningSession(
            id=payload.session_id,
            agent_id=payload.agent_id,
            engagement_id=agent.engagement_id,
        )
        session.add(mining_session)
        await session.flush()

    # Process events through the processor
    redis_client = request.app.state.redis_client
    from src.taskmining.processor import process_event_batch

    events_data = [
        {
            "event_type": e.event_type.value,
            "timestamp": e.timestamp.isoformat(),
            "application_name": e.application_name,
            "window_title": e.window_title,
            "event_data": e.event_data,
            "idempotency_key": e.idempotency_key,
        }
        for e in payload.events
    ]

    result_counts = await process_event_batch(
        session=session,
        redis_client=redis_client,
        session_id=payload.session_id,
        engagement_id=agent.engagement_id,
        events=events_data,
    )

    await session.commit()

    return result_counts


# ---------------------------------------------------------------------------
# GET /config/{agent_id}
# ---------------------------------------------------------------------------


@router.get("/config/{agent_id}", response_model=CaptureConfig)
async def get_agent_config(
    agent_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:read")),
) -> dict[str, Any]:
    """Return capture configuration for an agent.

    Agents poll this endpoint to get updated capture policies.
    """
    result = await session.execute(select(TaskMiningAgent).where(TaskMiningAgent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    config = agent.config_json or {}
    return {
        "capture_granularity": agent.capture_granularity.value,
        "app_allowlist": config.get("app_allowlist"),
        "app_blocklist": config.get("app_blocklist"),
        "url_domain_only": config.get("url_domain_only", True),
        "screenshot_enabled": config.get("screenshot_enabled", False),
        "screenshot_interval_seconds": config.get("screenshot_interval_seconds", 30),
        "batch_size": config.get("batch_size", 1000),
        "batch_interval_seconds": config.get("batch_interval_seconds", 30),
        "idle_timeout_seconds": config.get("idle_timeout_seconds", 300),
        "pii_patterns_version": config.get("pii_patterns_version", "1.0"),
    }


# ---------------------------------------------------------------------------
# POST /heartbeat
# ---------------------------------------------------------------------------


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def agent_heartbeat(
    payload: HeartbeatRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:write")),
) -> dict[str, Any]:
    """Accept a heartbeat from an agent and return status/config updates."""
    result = await session.execute(select(TaskMiningAgent).where(TaskMiningAgent.id == payload.agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    now = datetime.now(UTC)
    agent.last_heartbeat_at = now
    await session.commit()

    # Check if agent should auto-disable
    response_status = "ok"
    if agent.status == AgentStatus.REVOKED:
        response_status = "revoked"
    elif agent.engagement_end_date and now > agent.engagement_end_date:
        agent.status = AgentStatus.EXPIRED
        await session.commit()
        response_status = "expired"

    return {
        "status": response_status,
        "server_time": now.isoformat(),
        "config_updated": False,
        "config": None,
    }


# ---------------------------------------------------------------------------
# GET /sessions
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    engagement_id: UUID | None = None,
    agent_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:read")),
) -> dict[str, Any]:
    """List capture sessions with optional filters."""
    query = select(TaskMiningSession)
    count_query = select(func.count(TaskMiningSession.id))

    if engagement_id:
        query = query.where(TaskMiningSession.engagement_id == engagement_id)
        count_query = count_query.where(TaskMiningSession.engagement_id == engagement_id)
    if agent_id:
        query = query.where(TaskMiningSession.agent_id == agent_id)
        count_query = count_query.where(TaskMiningSession.agent_id == agent_id)

    query = query.order_by(TaskMiningSession.started_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    sessions = [_session_to_response(s) for s in result.scalars().all()]

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    return {"items": sessions, "total": total}


# ---------------------------------------------------------------------------
# GET /actions
# ---------------------------------------------------------------------------


@router.get("/actions", response_model=ActionListResponse)
async def list_actions(
    engagement_id: UUID | None = None,
    session_id: UUID | None = None,
    category: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:read")),
) -> dict[str, Any]:
    """List aggregated user actions with optional filters."""
    query = select(TaskMiningAction)
    count_query = select(func.count(TaskMiningAction.id))

    if engagement_id:
        query = query.where(TaskMiningAction.engagement_id == engagement_id)
        count_query = count_query.where(TaskMiningAction.engagement_id == engagement_id)
    if session_id:
        query = query.where(TaskMiningAction.session_id == session_id)
        count_query = count_query.where(TaskMiningAction.session_id == session_id)
    if category:
        query = query.where(TaskMiningAction.category == category)
        count_query = count_query.where(TaskMiningAction.category == category)

    query = query.order_by(TaskMiningAction.started_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    actions = [_action_to_response(a) for a in result.scalars().all()]

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    return {"items": actions, "total": total}


# ---------------------------------------------------------------------------
# GET /quarantine
# ---------------------------------------------------------------------------


@router.get("/quarantine", response_model=QuarantineListResponse)
async def list_quarantine(
    engagement_id: UUID | None = None,
    status_filter: QuarantineStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:admin")),
) -> dict[str, Any]:
    """List PII quarantine items for review."""
    query = select(PIIQuarantine)
    count_query = select(func.count(PIIQuarantine.id))

    if engagement_id:
        query = query.where(PIIQuarantine.engagement_id == engagement_id)
        count_query = count_query.where(PIIQuarantine.engagement_id == engagement_id)
    if status_filter:
        query = query.where(PIIQuarantine.status == status_filter)
        count_query = count_query.where(PIIQuarantine.status == status_filter)

    query = query.order_by(PIIQuarantine.created_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    items = [_quarantine_to_response(q) for q in result.scalars().all()]

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    return {"items": items, "total": total}


# ---------------------------------------------------------------------------
# POST /quarantine/{quarantine_id}/action
# ---------------------------------------------------------------------------


@router.post("/quarantine/{quarantine_id}/action", response_model=QuarantineItemResponse)
async def quarantine_action(
    quarantine_id: UUID,
    payload: QuarantineActionRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:admin")),
) -> dict[str, Any]:
    """Release or delete a quarantined event."""
    if payload.action not in ("release", "delete"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Action must be 'release' or 'delete'",
        )

    result = await session.execute(select(PIIQuarantine).where(PIIQuarantine.id == quarantine_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quarantine item not found")

    now = datetime.now(UTC)
    if payload.action == "release":
        item.status = QuarantineStatus.RELEASED
        item.reviewed_at = now
        item.reviewed_by = current_user.email
    else:
        item.status = QuarantineStatus.DELETED
        item.reviewed_at = now
        item.reviewed_by = current_user.email

    await session.commit()
    await session.refresh(item)

    logger.info("Quarantine item %s action: %s", quarantine_id, payload.action)
    return _quarantine_to_response(item)


# ---------------------------------------------------------------------------
# GET /dashboard/stats
# ---------------------------------------------------------------------------


@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    engagement_id: UUID | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:read")),
) -> dict[str, Any]:
    """Return aggregated dashboard statistics for task mining."""
    filters = []
    if engagement_id:
        filters.append(TaskMiningAgent.engagement_id == engagement_id)

    # Agent counts
    total_agents_q = select(func.count(TaskMiningAgent.id))
    active_agents_q = select(func.count(TaskMiningAgent.id)).where(TaskMiningAgent.status == AgentStatus.ACTIVE)
    if filters:
        total_agents_q = total_agents_q.where(*filters)
        active_agents_q = active_agents_q.where(*filters)

    total_agents = (await session.execute(total_agents_q)).scalar() or 0
    active_agents = (await session.execute(active_agents_q)).scalar() or 0

    # Session counts
    session_filters = []
    if engagement_id:
        session_filters.append(TaskMiningSession.engagement_id == engagement_id)

    total_sessions_q = select(func.count(TaskMiningSession.id))
    active_sessions_q = select(func.count(TaskMiningSession.id)).where(TaskMiningSession.status == SessionStatus.ACTIVE)
    if session_filters:
        total_sessions_q = total_sessions_q.where(*session_filters)
        active_sessions_q = active_sessions_q.where(*session_filters)

    total_sessions = (await session.execute(total_sessions_q)).scalar() or 0
    active_sessions = (await session.execute(active_sessions_q)).scalar() or 0

    # Event/action counts
    event_filters = []
    if engagement_id:
        event_filters.append(TaskMiningEvent.engagement_id == engagement_id)

    total_events_q = select(func.count(TaskMiningEvent.id))
    if event_filters:
        total_events_q = total_events_q.where(*event_filters)
    total_events = (await session.execute(total_events_q)).scalar() or 0

    action_filters = []
    if engagement_id:
        action_filters.append(TaskMiningAction.engagement_id == engagement_id)

    total_actions_q = select(func.count(TaskMiningAction.id))
    if action_filters:
        total_actions_q = total_actions_q.where(*action_filters)
    total_actions = (await session.execute(total_actions_q)).scalar() or 0

    # PII stats
    pii_filters = []
    if engagement_id:
        pii_filters.append(PIIQuarantine.engagement_id == engagement_id)

    total_pii_q = select(func.count(PIIQuarantine.id))
    pending_pii_q = select(func.count(PIIQuarantine.id)).where(PIIQuarantine.status == QuarantineStatus.PENDING_REVIEW)
    if pii_filters:
        total_pii_q = total_pii_q.where(*pii_filters)
        pending_pii_q = pending_pii_q.where(*pii_filters)

    total_pii = (await session.execute(total_pii_q)).scalar() or 0
    pending_pii = (await session.execute(pending_pii_q)).scalar() or 0

    # Events in last 24h
    cutoff_24h = datetime.now(UTC) - timedelta(hours=24)
    events_24h_q = select(func.count(TaskMiningEvent.id)).where(TaskMiningEvent.created_at >= cutoff_24h)
    if event_filters:
        events_24h_q = events_24h_q.where(*event_filters)
    events_24h = (await session.execute(events_24h_q)).scalar() or 0

    # App usage heatmap (top 10 apps by event count)
    app_usage_q = (
        select(
            TaskMiningEvent.application_name,
            func.count(TaskMiningEvent.id).label("event_count"),
        )
        .where(TaskMiningEvent.application_name.isnot(None))
        .group_by(TaskMiningEvent.application_name)
        .order_by(func.count(TaskMiningEvent.id).desc())
        .limit(10)
    )
    if event_filters:
        app_usage_q = app_usage_q.where(*event_filters)

    app_usage_result = await session.execute(app_usage_q)
    app_usage = [{"application": row[0], "event_count": row[1]} for row in app_usage_result.all()]

    return {
        "total_agents": total_agents,
        "active_agents": active_agents,
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "total_events": total_events,
        "total_actions": total_actions,
        "total_pii_detections": total_pii,
        "quarantine_pending": pending_pii,
        "events_last_24h": events_24h,
        "app_usage": app_usage,
    }


# ---------------------------------------------------------------------------
# VCE helpers
# ---------------------------------------------------------------------------


def _vce_to_response(vce: VisualContextEvent) -> dict[str, Any]:
    return {
        "id": str(vce.id),
        "engagement_id": str(vce.engagement_id),
        "session_id": str(vce.session_id) if vce.session_id else None,
        "agent_id": str(vce.agent_id) if vce.agent_id else None,
        "timestamp": vce.timestamp.isoformat(),
        "screen_state_class": vce.screen_state_class,
        "system_guess": vce.system_guess,
        "module_guess": vce.module_guess,
        "confidence": vce.confidence,
        "trigger_reason": vce.trigger_reason,
        "sensitivity_flags": vce.sensitivity_flags,
        "application_name": vce.application_name,
        "window_title_redacted": vce.window_title_redacted,
        "dwell_ms": vce.dwell_ms,
        "interaction_intensity": vce.interaction_intensity,
        "snapshot_ref": vce.snapshot_ref,
        "ocr_text_redacted": vce.ocr_text_redacted,
        "classification_method": vce.classification_method,
        "created_at": vce.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# POST /vce/events
# ---------------------------------------------------------------------------


@router.post("/vce/events", response_model=VCEBatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_vce_events(
    payload: VCEBatchRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:write")),
) -> dict[str, Any]:
    """Batch ingest VCE events from the agent.

    Events are validated and persisted individually. Invalid records are
    counted as rejected without blocking the rest of the batch.
    """
    from src.taskmining.vce.processor import process_vce_batch

    # Enrich each payload with agent_id from the batch envelope
    events_data = []
    for event in payload.events:
        data = event.model_dump()
        data["agent_id"] = str(payload.agent_id)
        events_data.append(data)

    counts = await process_vce_batch(session=session, events=events_data)
    await session.commit()

    logger.info(
        "VCE batch ingest: agent=%s accepted=%d rejected=%d",
        payload.agent_id,
        counts["accepted"],
        counts["rejected"],
    )
    return counts


# ---------------------------------------------------------------------------
# GET /vce
# ---------------------------------------------------------------------------


@router.get("/vce", response_model=VCEListResponse)
async def list_vce_events(
    engagement_id: UUID | None = None,
    session_id: UUID | None = None,
    screen_state_class: ScreenStateClass | None = None,
    trigger_reason: VCETriggerReason | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:read")),
) -> dict[str, Any]:
    """List VCE events with optional filters."""
    query = select(VisualContextEvent)
    count_query = select(func.count(VisualContextEvent.id))

    if engagement_id:
        query = query.where(VisualContextEvent.engagement_id == engagement_id)
        count_query = count_query.where(VisualContextEvent.engagement_id == engagement_id)
    if session_id:
        query = query.where(VisualContextEvent.session_id == session_id)
        count_query = count_query.where(VisualContextEvent.session_id == session_id)
    if screen_state_class:
        query = query.where(VisualContextEvent.screen_state_class == screen_state_class)
        count_query = count_query.where(VisualContextEvent.screen_state_class == screen_state_class)
    if trigger_reason:
        query = query.where(VisualContextEvent.trigger_reason == trigger_reason)
        count_query = count_query.where(VisualContextEvent.trigger_reason == trigger_reason)

    query = query.order_by(VisualContextEvent.timestamp.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    items = [_vce_to_response(v) for v in result.scalars().all()]

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    return {"items": items, "total": total}


# ---------------------------------------------------------------------------
# GET /vce/{vce_id}
# ---------------------------------------------------------------------------


@router.get("/vce/{vce_id}", response_model=VCEResponse)
async def get_vce_event(
    vce_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:read")),
) -> dict[str, Any]:
    """Get a single VCE event by ID."""
    result = await session.execute(select(VisualContextEvent).where(VisualContextEvent.id == vce_id))
    vce = result.scalar_one_or_none()
    if vce is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VCE event not found")
    return _vce_to_response(vce)


# ---------------------------------------------------------------------------
# GET /vce/distribution
# ---------------------------------------------------------------------------


@router.get("/vce/distribution", response_model=VCEDistributionResponse)
async def get_vce_distribution(
    engagement_id: UUID,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:read")),
) -> dict[str, Any]:
    """Return screen state class distribution for an engagement."""
    from src.taskmining.vce.analytics import get_vce_distribution as _get_distribution

    return await _get_distribution(
        session=session,
        engagement_id=engagement_id,
        period_start=period_start,
        period_end=period_end,
    )


# ---------------------------------------------------------------------------
# GET /vce/triggers/summary
# ---------------------------------------------------------------------------


@router.get("/vce/triggers/summary", response_model=VCETriggerSummaryResponse)
async def get_vce_trigger_summary(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:read")),
) -> dict[str, Any]:
    """Return trigger reason distribution for an engagement."""
    from src.taskmining.vce.analytics import get_trigger_summary

    return await get_trigger_summary(session=session, engagement_id=engagement_id)


# ---------------------------------------------------------------------------
# GET /vce/dwell
# ---------------------------------------------------------------------------


@router.get("/vce/dwell", response_model=VCEDwellAnalysisResponse)
async def get_vce_dwell_analysis(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:read")),
) -> dict[str, Any]:
    """Return dwell time analysis per app and screen state class."""
    from src.taskmining.vce.analytics import get_dwell_analysis

    return await get_dwell_analysis(session=session, engagement_id=engagement_id)


# ---------------------------------------------------------------------------
# Switching Sequences
# ---------------------------------------------------------------------------


def _trace_to_response(t: SwitchingTrace) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "engagement_id": str(t.engagement_id),
        "session_id": str(t.session_id) if t.session_id else None,
        "role_id": str(t.role_id) if t.role_id else None,
        "trace_sequence": t.trace_sequence,
        "dwell_durations": t.dwell_durations,
        "total_duration_ms": t.total_duration_ms,
        "friction_score": t.friction_score,
        "is_ping_pong": t.is_ping_pong,
        "ping_pong_count": t.ping_pong_count,
        "app_count": t.app_count,
        "started_at": t.started_at.isoformat(),
        "ended_at": t.ended_at.isoformat(),
        "created_at": t.created_at.isoformat(),
    }


def _matrix_to_response(m: TransitionMatrix) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "engagement_id": str(m.engagement_id),
        "role_id": str(m.role_id) if m.role_id else None,
        "period_start": m.period_start.isoformat(),
        "period_end": m.period_end.isoformat(),
        "matrix_data": m.matrix_data,
        "total_transitions": m.total_transitions,
        "unique_apps": m.unique_apps,
        "top_transitions": m.top_transitions,
        "created_at": m.created_at.isoformat(),
    }


@router.get("/switching/traces", response_model=SwitchingTraceListResponse)
async def list_switching_traces(
    engagement_id: UUID,
    session_id: UUID | None = None,
    min_friction: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:read")),
) -> dict[str, Any]:
    """List switching traces for an engagement."""
    query = select(SwitchingTrace).where(SwitchingTrace.engagement_id == engagement_id)
    count_query = select(func.count(SwitchingTrace.id)).where(SwitchingTrace.engagement_id == engagement_id)

    if session_id is not None:
        query = query.where(SwitchingTrace.session_id == session_id)
        count_query = count_query.where(SwitchingTrace.session_id == session_id)
    if min_friction is not None:
        query = query.where(SwitchingTrace.friction_score >= min_friction)
        count_query = count_query.where(SwitchingTrace.friction_score >= min_friction)

    query = query.order_by(SwitchingTrace.started_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    traces = [_trace_to_response(t) for t in result.scalars().all()]

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return {"items": traces, "total": total}


@router.get("/switching/matrix", response_model=TransitionMatrixResponse)
async def get_transition_matrix(
    engagement_id: UUID,
    period_start: datetime,
    period_end: datetime,
    role_id: UUID | None = None,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:read")),
) -> dict[str, Any]:
    """Get or compute a transition matrix for an engagement period.

    Returns the most recent stored matrix matching the filters, or computes
    a new one if none exists.
    """
    # Try to find existing matrix for this period
    query = (
        select(TransitionMatrix)
        .where(
            TransitionMatrix.engagement_id == engagement_id,
            TransitionMatrix.period_start == period_start,
            TransitionMatrix.period_end == period_end,
        )
        .order_by(TransitionMatrix.created_at.desc())
        .limit(1)
    )
    if role_id is not None:
        query = query.where(TransitionMatrix.role_id == role_id)

    result = await db.execute(query)
    matrix = result.scalar_one_or_none()

    if matrix is None:
        from src.taskmining.switching import compute_transition_matrix

        matrix = await compute_transition_matrix(
            session=db,
            engagement_id=engagement_id,
            role_id=role_id,
            period_start=period_start,
            period_end=period_end,
        )
        await db.commit()
        await db.refresh(matrix)

    return _matrix_to_response(matrix)


@router.get("/switching/friction", response_model=FrictionAnalysisResponse)
async def get_friction_analysis(
    engagement_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:read")),
) -> dict[str, Any]:
    """Return aggregate friction analysis for an engagement."""
    from src.taskmining.switching import get_friction_analysis as _get_friction_analysis

    return await _get_friction_analysis(session=db, engagement_id=engagement_id)


@router.post("/switching/assemble", response_model=AssembleSwitchingResponse)
async def assemble_switching(
    payload: AssembleSwitchingRequest,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_permission("taskmining:write")),
) -> dict[str, Any]:
    """Trigger switching trace assembly for an engagement.

    Assembles APP_SWITCH events into SwitchingTrace records. Idempotent:
    duplicate events are skipped by the service layer.
    """
    from src.taskmining.switching import assemble_switching_traces

    traces = await assemble_switching_traces(
        session=db,
        engagement_id=payload.engagement_id,
        session_id=payload.session_id,
    )
    await db.commit()

    logger.info("Assembled %d switching traces for engagement %s", len(traces), payload.engagement_id)
    return {"traces_created": len(traces), "status": "ok"}
