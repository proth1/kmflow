"""Camunda (CIB7) BPMN engine API routes.

Provides endpoints for managing BPMN process deployments,
starting process instances, and querying user tasks.
"""

from __future__ import annotations

import logging
from typing import Any  # noqa: F401 — used in inline Pydantic schemas

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel

from src.core.models import User
from src.core.permissions import require_permission

# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class _CamundaBase(BaseModel):
    """Base model for Camunda passthrough responses.

    ``extra="allow"`` preserves all camelCase fields returned by the
    Camunda REST API without requiring each one to be declared explicitly.
    """

    model_config = {"extra": "allow"}

    id: str | None = None
    name: str | None = None


class DeploymentResponse(_CamundaBase):
    """Response schema for a single Camunda deployment."""

    source: str | None = None


class ProcessDefinitionResponse(_CamundaBase):
    """Response schema for a Camunda process definition."""

    key: str | None = None
    version: int | None = None


class ProcessInstanceResponse(_CamundaBase):
    """Response schema for a Camunda process instance."""

    suspended: bool | None = None


class UserTaskResponse(_CamundaBase):
    """Response schema for a Camunda user task."""

    assignee: str | None = None
    created: str | None = None
    due: str | None = None
    priority: int | None = None


class StartProcessResponse(_CamundaBase):
    """Response schema for starting a process instance."""

    suspended: bool | None = None


class DeployProcessResponse(_CamundaBase):
    """Response schema for deploying a single BPMN file."""


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


@router.get("/deployments", response_model=list[DeploymentResponse])
async def list_deployments(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_permission("engagement:read")),
) -> list[dict[str, Any]]:
    """List all BPMN process deployments."""
    client = _get_camunda_client(request)
    try:
        return await client.list_deployments(max_results=limit, first_result=offset)
    except (ConnectionError, OSError, httpx.HTTPError) as e:
        logger.error("Failed to list deployments: %s", e)
        raise HTTPException(status_code=502, detail="Failed to communicate with Camunda engine") from e


@router.post("/deploy", response_model=DeployProcessResponse, status_code=status.HTTP_200_OK)
async def deploy_process(
    request: Request,
    file: UploadFile = File(...),
    deployment_name: str = "kmflow-deployment",
    user: User = Depends(require_permission("engagement:update")),
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
    except (ConnectionError, OSError, httpx.HTTPError) as e:
        logger.error("Failed to deploy process: %s", e)
        raise HTTPException(status_code=502, detail="Failed to deploy process to Camunda engine") from e


@router.get("/process-definitions", response_model=list[ProcessDefinitionResponse])
async def list_process_definitions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_permission("engagement:read")),
) -> list[dict[str, Any]]:
    """List all deployed process definitions (latest versions)."""
    client = _get_camunda_client(request)
    try:
        return await client.list_process_definitions(max_results=limit, first_result=offset)
    except (ConnectionError, OSError, httpx.HTTPError) as e:
        logger.error("Failed to list process definitions: %s", e)
        raise HTTPException(status_code=502, detail="Failed to communicate with Camunda engine") from e


@router.post("/process/{key}/start", response_model=StartProcessResponse, status_code=status.HTTP_200_OK)
async def start_process(
    key: str,
    body: StartProcessRequest,
    request: Request,
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Start a new process instance by process definition key."""
    client = _get_camunda_client(request)
    try:
        return await client.start_process(key, variables=body.variables)
    except (ConnectionError, OSError, httpx.HTTPError) as e:
        logger.error("Failed to start process %s: %s", key, e)
        raise HTTPException(status_code=502, detail=f"Failed to start process '{key}'") from e


@router.get("/process-instances", response_model=list[ProcessInstanceResponse])
async def get_process_instances(
    request: Request,
    active: bool = True,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_permission("engagement:read")),
) -> list[dict[str, Any]]:
    """Get process instances."""
    client = _get_camunda_client(request)
    try:
        return await client.get_process_instances(active=active, max_results=limit, first_result=offset)
    except (ConnectionError, OSError, httpx.HTTPError) as e:
        logger.error("Failed to get process instances: %s", e)
        raise HTTPException(status_code=502, detail="Failed to communicate with Camunda engine") from e


@router.get("/tasks", response_model=list[UserTaskResponse])
async def get_tasks(
    request: Request,
    assignee: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_permission("engagement:read")),
) -> list[dict[str, Any]]:
    """Get user tasks."""
    client = _get_camunda_client(request)
    try:
        return await client.get_tasks(assignee=assignee, max_results=limit, first_result=offset)
    except (ConnectionError, OSError, httpx.HTTPError) as e:
        logger.error("Failed to get tasks: %s", e)
        raise HTTPException(status_code=502, detail="Failed to communicate with Camunda engine") from e
