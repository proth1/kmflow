"""Export watermarking API routes (Story #387).

Provides endpoints for querying the export log and extracting
watermarks from recovered documents.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import User
from src.core.permissions import require_engagement_access, require_permission
from src.security.watermark.extractor import WatermarkExtractor
from src.security.watermark.service import WatermarkService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/exports", tags=["exports"])


class WatermarkExtractPayload(BaseModel):
    """Payload for watermark extraction requests."""

    encoded_watermark: str


@router.get("")
async def list_exports(
    engagement_id: UUID = Query(..., description="Engagement to query exports for"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("export:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get paginated export logs for an engagement.

    Restricted to roles with export:read permission (engagement_lead, platform_admin).
    """

    service = WatermarkService(session)
    return await service.get_export_logs(engagement_id, limit, offset)


@router.post("/extract-watermark")
async def extract_watermark(
    payload: WatermarkExtractPayload,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("export:read")),
) -> dict[str, Any]:
    """Extract and verify an invisible watermark from a recovered document.

    Used for forensic identification of the source of leaked documents.
    Returns the decoded watermark payload and matching export log entry.
    """

    extractor = WatermarkExtractor(session)
    result = await extractor.extract_from_encoded(payload.encoded_watermark)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid or tampered watermark — could not decode or verify HMAC",
        )

    return result
