"""Admin API routes for platform management.

Provides:
- POST /api/v1/admin/retention-cleanup    (platform_admin only)
- POST /api/v1/admin/rotate-encryption-key (platform_admin only)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import User, UserRole
from src.core.permissions import require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class RetentionPreviewItem(BaseModel):
    id: str
    name: str


class RetentionCleanupResponse(BaseModel):
    dry_run: bool
    status: str
    would_clean_up: int | None = None
    engagements: list[RetentionPreviewItem] | None = None
    cleaned_up: int | None = None


class KeyRotationResponse(BaseModel):
    rotated: int
    total: int
    status: str


@router.post("/retention-cleanup", response_model=RetentionCleanupResponse, status_code=status.HTTP_200_OK)
async def run_retention_cleanup(
    user: User = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    session: AsyncSession = Depends(get_session),
    dry_run: bool = Query(default=True),
    x_confirm_action: str | None = Header(default=None),
) -> RetentionCleanupResponse:
    """Trigger data retention cleanup for expired engagements.

    Finds engagements where created_at + retention_days < now
    and archives them. Platform admin only.

    Use ?dry_run=true (default) to preview which engagements would be affected.
    Set ?dry_run=false AND provide header X-Confirm-Action: retention-cleanup
    to execute the cleanup.
    """
    from src.core.retention import cleanup_expired_engagements, find_expired_engagements

    if dry_run:
        expired = await find_expired_engagements(session)
        return RetentionCleanupResponse(
            dry_run=True,
            would_clean_up=len(expired),
            engagements=[RetentionPreviewItem(id=str(eng.id), name=eng.name) for eng in expired],
            status="preview",
        )

    if x_confirm_action != "retention-cleanup":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide header X-Confirm-Action: retention-cleanup to execute cleanup",
        )

    count = await cleanup_expired_engagements(session)
    return RetentionCleanupResponse(dry_run=False, cleaned_up=count, status="completed")


@router.post("/rotate-encryption-key", response_model=KeyRotationResponse, status_code=status.HTTP_200_OK)
async def rotate_encryption_key(
    user: User = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> KeyRotationResponse:
    """Re-encrypt all integration credentials with the current key.

    Requires ENCRYPTION_KEY_PREVIOUS to be set to the old key and
    ENCRYPTION_KEY to be set to the new key. Re-encrypts all
    integration_connections.encrypted_config values atomically —
    if any credential fails to re-encrypt, the entire batch is rolled back.
    """
    from sqlalchemy import select

    from src.core.encryption import re_encrypt_value
    from src.core.models import IntegrationConnection

    result = await session.execute(
        select(IntegrationConnection).where(IntegrationConnection.encrypted_config.isnot(None))
    )
    connections = result.scalars().all()

    try:
        rotated = 0
        for conn in connections:
            if conn.encrypted_config:
                new_config = re_encrypt_value(conn.encrypted_config)
                conn.encrypted_config = new_config
                rotated += 1

        await session.commit()
    except (SQLAlchemyError, ValueError) as e:
        await session.rollback()
        logger.error("Key rotation failed after %d credentials, rolled back: %s", rotated, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Key rotation failed and was rolled back. {rotated} credentials were NOT persisted.",
        ) from e

    return KeyRotationResponse(rotated=rotated, total=len(connections), status="completed")
