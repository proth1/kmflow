"""Admin API routes for platform management.

Provides:
- POST /api/v1/admin/retention-cleanup    (platform_admin only)
- POST /api/v1/admin/rotate-encryption-key (platform_admin only)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import User
from src.core.permissions import require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


async def get_session(request: Request):
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session


@router.post("/retention-cleanup")
async def run_retention_cleanup(
    user: User = Depends(require_role("platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Trigger data retention cleanup for expired engagements.

    Finds engagements where created_at + retention_days < now
    and archives them. Platform admin only.
    """
    from src.core.retention import cleanup_expired_engagements

    count = await cleanup_expired_engagements(session)
    return {"cleaned_up": count, "status": "completed"}


@router.post("/rotate-encryption-key")
async def rotate_encryption_key(
    user: User = Depends(require_role("platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Re-encrypt all integration credentials with the current key.

    Requires ENCRYPTION_KEY_PREVIOUS to be set to the old key and
    ENCRYPTION_KEY to be set to the new key. Re-encrypts all
    integration_connections.encrypted_config values.
    """
    from sqlalchemy import select, update

    from src.core.encryption import re_encrypt_value
    from src.core.models import IntegrationConnection

    result = await session.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.encrypted_config.isnot(None)
        )
    )
    connections = result.scalars().all()

    rotated = 0
    errors = 0
    for conn in connections:
        try:
            new_config = re_encrypt_value(conn.encrypted_config)
            conn.encrypted_config = new_config
            rotated += 1
        except Exception as e:
            logger.error("Failed to re-encrypt connection %s: %s", conn.id, e)
            errors += 1

    if rotated:
        await session.commit()

    return {
        "rotated": rotated,
        "errors": errors,
        "status": "completed" if errors == 0 else "completed_with_errors",
    }
