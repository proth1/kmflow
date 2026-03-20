"""Deployment configuration API routes (KMFLOW-7).

Exposes deployment capabilities and health information so the frontend
can adapt its UI based on what features are available (e.g. hide copilot
when no LLM is configured, show data residency warnings).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.middleware.data_residency import get_deployment_capabilities
from src.core.auth import get_current_user
from src.core.models import User

router = APIRouter(prefix="/api/v1/deployment", tags=["deployment"])


class DeploymentCapabilitiesResponse(BaseModel):
    """Response schema for deployment capabilities."""

    llm_enabled: bool = False
    neo4j_enabled: bool = False
    minio_enabled: bool = False
    data_residency: str = "none"
    environment: str = "unknown"


@router.get("/capabilities", response_model=DeploymentCapabilitiesResponse)
async def capabilities(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return deployment capabilities.

    Used by the frontend to determine which features are available
    in this deployment (cloud vs. on-prem vs. air-gapped).
    """
    return get_deployment_capabilities()
