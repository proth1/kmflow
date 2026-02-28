"""MCP server with SSE transport.

Provides an MCP-compatible server mounted as a FastAPI sub-application
with Server-Sent Events (SSE) transport for streaming tool results.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from src.mcp.auth import validate_api_key
from src.mcp.schemas import MCPServerInfo, MCPToolCall, MCPToolResult
from src.mcp.tools import TOOL_DEFINITIONS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


async def _verify_mcp_auth(request: Request) -> dict[str, Any]:
    """Verify MCP API key from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    api_key = auth[7:]
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        client = await validate_api_key(session, api_key)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return client


@router.get("/info", response_model=MCPServerInfo)
async def server_info(
    client: dict[str, Any] = Depends(_verify_mcp_auth),
) -> dict[str, Any]:
    """Get MCP server information and available tools."""
    return {
        "name": "kmflow",
        "version": "0.1.0",
        "description": "KMFlow Process Intelligence Platform",
        "tools": TOOL_DEFINITIONS,
    }


@router.post("/tools/call", response_model=MCPToolResult)
async def call_tool(
    payload: MCPToolCall,
    request: Request,
    client: dict[str, Any] = Depends(_verify_mcp_auth),
) -> dict[str, Any]:
    """Execute an MCP tool call."""
    tool_name = payload.tool_name
    args = payload.arguments

    # Validate tool exists
    valid_tools = {t["name"] for t in TOOL_DEFINITIONS}
    if tool_name not in valid_tools:
        return {
            "request_id": payload.request_id,
            "tool_name": tool_name,
            "success": False,
            "error": f"Unknown tool: {tool_name}. Available: {sorted(valid_tools)}",
        }

    try:
        result = await _execute_tool(tool_name, args, request)
        return {
            "request_id": payload.request_id,
            "tool_name": tool_name,
            "success": True,
            "result": result,
        }
    except (ValueError, RuntimeError) as e:
        logger.exception("MCP tool execution failed: %s", tool_name)
        return {
            "request_id": payload.request_id,
            "tool_name": tool_name,
            "success": False,
            "error": str(e),
        }


@router.post("/tools/call/stream")
async def call_tool_stream(
    payload: MCPToolCall,
    request: Request,
    client: dict[str, Any] = Depends(_verify_mcp_auth),
) -> StreamingResponse:
    """Execute an MCP tool call with SSE streaming response."""

    async def event_stream():
        yield f"data: {json.dumps({'type': 'start', 'tool_name': payload.tool_name})}\n\n"

        try:
            result = await _execute_tool(payload.tool_name, payload.arguments, request)
            yield f"data: {json.dumps({'type': 'result', 'data': result})}\n\n"
        except Exception as e:  # Intentionally broad: SSE generator must catch all errors to send done event
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/tools")
async def list_tools(
    client: dict[str, Any] = Depends(_verify_mcp_auth),
) -> list[dict[str, Any]]:
    """List available MCP tools."""
    return TOOL_DEFINITIONS


async def _execute_tool(
    tool_name: str,
    args: dict[str, Any],
    request: Request,
) -> Any:
    """Execute an MCP tool by dispatching to the appropriate handler."""
    # Get database session
    session_factory = request.app.state.db_session_factory

    if tool_name == "get_engagement":
        return await _tool_get_engagement(session_factory, args)
    elif tool_name == "list_evidence":
        return await _tool_list_evidence(session_factory, args)
    elif tool_name == "get_process_model":
        return await _tool_get_process_model(session_factory, args)
    elif tool_name == "get_gaps":
        return await _tool_get_gaps(session_factory, args)
    elif tool_name == "get_monitoring_status":
        return await _tool_get_monitoring_status(session_factory, args)
    elif tool_name == "get_deviations":
        return await _tool_get_deviations(session_factory, args)
    elif tool_name == "search_patterns":
        return await _tool_search_patterns(session_factory, args)
    elif tool_name == "run_simulation":
        return await _tool_run_simulation(session_factory, args)
    else:
        raise ValueError(f"Unhandled tool: {tool_name}")


async def _tool_get_engagement(session_factory: Any, args: dict[str, Any]) -> dict[str, Any]:
    from uuid import UUID

    from sqlalchemy import func, select

    from src.core.models import Engagement, EvidenceItem

    eid = UUID(args["engagement_id"])
    async with session_factory() as session:
        result = await session.execute(select(Engagement).where(Engagement.id == eid))
        eng = result.scalar_one_or_none()
        if not eng:
            return {"error": "Engagement not found"}

        count = (
            await session.execute(select(func.count(EvidenceItem.id)).where(EvidenceItem.engagement_id == eid))
        ).scalar() or 0

        return {
            "id": str(eng.id),
            "name": eng.name,
            "client": eng.client,
            "status": eng.status.value if hasattr(eng.status, "value") else str(eng.status),
            "evidence_count": count,
        }


async def _tool_list_evidence(session_factory: Any, args: dict[str, Any]) -> dict[str, Any]:
    from uuid import UUID

    from sqlalchemy import select

    from src.core.models import EvidenceItem

    eid = UUID(args["engagement_id"])
    limit = args.get("limit", 20)
    async with session_factory() as session:
        query = select(EvidenceItem).where(EvidenceItem.engagement_id == eid).limit(limit)
        result = await session.execute(query)
        items = [
            {
                "id": str(e.id),
                "name": e.name,
                "category": e.category.value if hasattr(e.category, "value") else str(e.category),
            }
            for e in result.scalars().all()
        ]
        return {"items": items, "total": len(items)}


async def _tool_get_process_model(session_factory: Any, args: dict[str, Any]) -> dict[str, Any]:
    from uuid import UUID

    from sqlalchemy import select

    from src.core.models import ProcessModel

    eid = UUID(args["engagement_id"])
    async with session_factory() as session:
        result = await session.execute(
            select(ProcessModel)
            .where(ProcessModel.engagement_id == eid)
            .order_by(ProcessModel.created_at.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        if not model:
            return {"model": None}
        return {
            "id": str(model.id),
            "scope": model.scope,
            "confidence_score": model.confidence_score,
            "element_count": model.element_count,
        }


async def _tool_get_gaps(session_factory: Any, args: dict[str, Any]) -> dict[str, Any]:
    from uuid import UUID

    from sqlalchemy import select

    from src.core.models import GapAnalysisResult

    eid = UUID(args["engagement_id"])
    async with session_factory() as session:
        result = await session.execute(select(GapAnalysisResult).where(GapAnalysisResult.engagement_id == eid))
        gaps = [
            {
                "id": str(g.id),
                "dimension": g.dimension.value if hasattr(g.dimension, "value") else str(g.dimension),
                "gap_type": g.gap_type.value if hasattr(g.gap_type, "value") else str(g.gap_type),
                "severity": g.severity,
            }
            for g in result.scalars().all()
        ]
        return {"gaps": gaps, "total": len(gaps)}


async def _tool_get_monitoring_status(session_factory: Any, args: dict[str, Any]) -> dict[str, Any]:
    from uuid import UUID

    from sqlalchemy import func, select

    from src.core.models import AlertStatus, MonitoringAlert, MonitoringJob, MonitoringStatus

    eid = UUID(args["engagement_id"])
    async with session_factory() as session:
        active = (
            await session.execute(
                select(func.count(MonitoringJob.id)).where(
                    MonitoringJob.engagement_id == eid, MonitoringJob.status == MonitoringStatus.ACTIVE
                )
            )
        ).scalar() or 0
        open_alerts = (
            await session.execute(
                select(func.count(MonitoringAlert.id)).where(
                    MonitoringAlert.engagement_id == eid,
                    MonitoringAlert.status.in_([AlertStatus.NEW, AlertStatus.ACKNOWLEDGED]),
                )
            )
        ).scalar() or 0
        return {"active_jobs": active, "open_alerts": open_alerts}


async def _tool_get_deviations(session_factory: Any, args: dict[str, Any]) -> dict[str, Any]:
    from uuid import UUID

    from sqlalchemy import select

    from src.core.models import ProcessDeviation

    eid = UUID(args["engagement_id"])
    limit = args.get("limit", 20)
    async with session_factory() as session:
        result = await session.execute(
            select(ProcessDeviation).where(ProcessDeviation.engagement_id == eid).limit(limit)
        )
        devs = [
            {
                "id": str(d.id),
                "category": d.category.value if hasattr(d.category, "value") else str(d.category),
                "magnitude": d.magnitude,
                "description": d.description,
            }
            for d in result.scalars().all()
        ]
        return {"deviations": devs, "total": len(devs)}


async def _tool_search_patterns(session_factory: Any, args: dict[str, Any]) -> dict[str, Any]:
    from sqlalchemy import select

    from src.core.models import PatternLibraryEntry

    async with session_factory() as session:
        query = select(PatternLibraryEntry).limit(10)
        result = await session.execute(query)
        patterns = [
            {
                "id": str(p.id),
                "title": p.title,
                "category": p.category.value if hasattr(p.category, "value") else str(p.category),
            }
            for p in result.scalars().all()
        ]
        return {"patterns": patterns, "total": len(patterns)}


async def _tool_run_simulation(session_factory: Any, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "simulation_queued",
        "scenario_name": args.get("scenario_name", ""),
        "simulation_type": args.get("simulation_type", ""),
    }
