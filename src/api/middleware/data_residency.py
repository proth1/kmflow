"""Data residency enforcement middleware (KMFLOW-7).

Provides a dependency that checks whether the current engagement's
data residency restriction permits external API calls.  When the
restriction is active (EU_ONLY, UK_ONLY, CUSTOM), the LLM provider
must be local and embedding generation must use on-device models.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.models.engagement import Engagement
from src.core.models.transfer import DataResidencyRestriction

logger = logging.getLogger(__name__)


async def check_data_residency(
    engagement_id: UUID,
    session: AsyncSession,
) -> DataResidencyRestriction:
    """Return the data residency restriction for an engagement.

    Raises HTTPException 403 if the platform's LLM provider is a cloud
    service and the engagement has a residency restriction.
    """
    result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    restriction = DataResidencyRestriction(engagement.data_residency_restriction)

    if restriction == DataResidencyRestriction.NONE:
        return restriction

    # Check if the LLM provider is local
    from src.core.llm import get_llm_provider

    llm = get_llm_provider()
    if not llm.is_local:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Engagement has data residency restriction '{restriction.value}'. "
                f"Current LLM provider ({llm.provider_type.value}) makes external API calls. "
                "Configure LLM_PROVIDER=ollama for a local LLM or contact your administrator."
            ),
        )

    return restriction


def get_deployment_capabilities() -> dict[str, bool | str]:
    """Return a summary of which capabilities are available.

    Used by the frontend to show/hide features based on deployment mode.
    """
    from src.core.llm import get_llm_provider

    settings = get_settings()
    llm = get_llm_provider()

    return {
        "llm_available": llm.provider_type.value != "stub",
        "llm_provider": llm.provider_type.value,
        "llm_is_local": llm.is_local,
        "embeddings_local": True,  # Always local (sentence-transformers)
        "data_residency_default": settings.default_data_residency,
        "copilot_enabled": llm.provider_type.value != "stub",
        "scenario_suggestions_enabled": llm.provider_type.value != "stub",
        "gap_rationale_enabled": llm.provider_type.value != "stub",
    }
