"""Deployment configuration API routes (KMFLOW-7).

Exposes deployment capabilities and health information so the frontend
can adapt its UI based on what features are available (e.g. hide copilot
when no LLM is configured, show data residency warnings).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.api.middleware.data_residency import get_deployment_capabilities

router = APIRouter(prefix="/api/v1/deployment", tags=["deployment"])


@router.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    """Return deployment capabilities.

    Used by the frontend to determine which features are available
    in this deployment (cloud vs. on-prem vs. air-gapped).
    """
    return get_deployment_capabilities()
