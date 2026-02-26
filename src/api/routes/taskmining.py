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
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.auth import get_current_user
from src.core.models import User
from src.core.permissions import require_permission
from src.api.schemas.taskmining import (
    ActionListResponse,
    ActionResponse,
    AgentApproveRequest,
    AgentListResponse,
    AgentRegisterRequest,
    AgentResponse,
    CaptureConfig,
    DashboardStats,
    EventBatchRequest,
    EventBatchResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    QuarantineActionRequest,
    QuarantineItemResponse,
    QuarantineListResponse,
    SessionListResponse,
    SessionResponse,
)
from src.core.models.taskmining import (
    AgentStatus,
    PIIQuarantine,
    QuarantineStatus,
    SessionStatus,
    TaskMiningAction,
    TaskMiningAgent,
    TaskMiningEvent,
    TaskMiningSession,
)

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
    result = await session.execute(
        select(TaskMiningAgent).where(TaskMiningAgent.id == payload.agent_id)
    )
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
    sess_result = await session.execute(
        select(TaskMiningSession).where(TaskMiningSession.id == payload.session_id)
    )
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
    result = await session.execute(
        select(TaskMiningAgent).where(TaskMiningAgent.id == agent_id)
    )
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
    result = await session.execute(
        select(TaskMiningAgent).where(TaskMiningAgent.id == payload.agent_id)
    )
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

    result = await session.execute(
        select(PIIQuarantine).where(PIIQuarantine.id == quarantine_id)
    )
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
    active_agents_q = select(func.count(TaskMiningAgent.id)).where(
        TaskMiningAgent.status == AgentStatus.ACTIVE
    )
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
    active_sessions_q = select(func.count(TaskMiningSession.id)).where(
        TaskMiningSession.status == SessionStatus.ACTIVE
    )
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
    pending_pii_q = select(func.count(PIIQuarantine.id)).where(
        PIIQuarantine.status == QuarantineStatus.PENDING_REVIEW
    )
    if pii_filters:
        total_pii_q = total_pii_q.where(*pii_filters)
        pending_pii_q = pending_pii_q.where(*pii_filters)

    total_pii = (await session.execute(total_pii_q)).scalar() or 0
    pending_pii = (await session.execute(pending_pii_q)).scalar() or 0

    # Events in last 24h
    cutoff_24h = datetime.now(UTC) - timedelta(hours=24)
    events_24h_q = select(func.count(TaskMiningEvent.id)).where(
        TaskMiningEvent.created_at >= cutoff_24h
    )
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
    app_usage = [
        {"application": row[0], "event_count": row[1]}
        for row in app_usage_result.all()
    ]

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
