"""Camunda (CIB7) BPMN engine API routes.

Provides endpoints for managing BPMN process deployments,
starting process instances, and querying user tasks.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/camunda", tags=["camunda"])


class StartProcessRequest(BaseModel):
    variables: dict[str, str] | None = None


def _get_camunda_client(request: Request):
    """Get the Camunda client from app state."""
    client = getattr(request.app.state, "camunda_client", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Camunda engine is not available",
        )
    return client


@router.get("/deployments")
async def list_deployments(request: Request) -> list[dict[str, Any]]:
    """List all BPMN process deployments."""
    client = _get_camunda_client(request)
    try:
        return await client.list_deployments()
    except Exception as e:
        logger.error("Failed to list deployments: %s", e)
        raise HTTPException(status_code=502, detail="Failed to communicate with Camunda engine")


@router.post("/deploy")
async def deploy_process(
    request: Request,
    file: UploadFile = File(...),
    deployment_name: str = "kmflow-deployment",
) -> dict[str, Any]:
    """Deploy a BPMN process model to the engine."""
    client = _get_camunda_client(request)
    try:
        content = await file.read()
        return await client.deploy_process(
            name=deployment_name,
            bpmn_xml=content,
            filename=file.filename or "process.bpmn",
        )
    except Exception as e:
        logger.error("Failed to deploy process: %s", e)
        raise HTTPException(status_code=502, detail="Failed to deploy process to Camunda engine")


@router.get("/process-definitions")
async def list_process_definitions(request: Request) -> list[dict[str, Any]]:
    """List all deployed process definitions (latest versions)."""
    client = _get_camunda_client(request)
    try:
        return await client.list_process_definitions()
    except Exception as e:
        logger.error("Failed to list process definitions: %s", e)
        raise HTTPException(status_code=502, detail="Failed to communicate with Camunda engine")


@router.post("/process/{key}/start")
async def start_process(
    key: str,
    body: StartProcessRequest,
    request: Request,
) -> dict[str, Any]:
    """Start a new process instance by process definition key."""
    client = _get_camunda_client(request)
    try:
        return await client.start_process(key, variables=body.variables)
    except Exception as e:
        logger.error("Failed to start process %s: %s", key, e)
        raise HTTPException(status_code=502, detail=f"Failed to start process '{key}'")


@router.get("/process-instances")
async def get_process_instances(
    request: Request,
    active: bool = True,
) -> list[dict[str, Any]]:
    """Get process instances."""
    client = _get_camunda_client(request)
    try:
        return await client.get_process_instances(active=active)
    except Exception as e:
        logger.error("Failed to get process instances: %s", e)
        raise HTTPException(status_code=502, detail="Failed to communicate with Camunda engine")


@router.get("/tasks")
async def get_tasks(
    request: Request,
    assignee: str | None = None,
) -> list[dict[str, Any]]:
    """Get user tasks."""
    client = _get_camunda_client(request)
    try:
        return await client.get_tasks(assignee=assignee)
    except Exception as e:
        logger.error("Failed to get tasks: %s", e)
        raise HTTPException(status_code=502, detail="Failed to communicate with Camunda engine")
