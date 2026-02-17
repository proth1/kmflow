"""Enhanced audit logging for security events.

Builds on the existing AuditLog model from Story #3.
Provides helper functions for logging security-related events
and a middleware for automatic request audit logging.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import AuditAction, AuditLog

logger = logging.getLogger(__name__)


async def log_security_event(
    session: AsyncSession,
    action: AuditAction,
    actor: str = "system",
    engagement_id: UUID | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
    resource: str | None = None,
) -> AuditLog | None:
    """Log a security-related audit event.

    For events that are not tied to a specific engagement (e.g. LOGIN),
    engagement_id can be None, and the event will be skipped if the
    AuditLog model requires a non-null engagement_id.

    Args:
        session: The database session.
        action: The audit action type.
        actor: Who performed the action (email or "system").
        engagement_id: The engagement this event relates to, if any.
        details: Additional context as a dict (serialized to JSON).
        ip_address: The client IP address.
        resource: The API resource being accessed.

    Returns:
        The created AuditLog entry, or None if engagement_id is required
        but not provided.
    """
    detail_parts = {}
    if details:
        detail_parts.update(details)
    if ip_address:
        detail_parts["ip_address"] = ip_address
    if resource:
        detail_parts["resource"] = resource

    detail_str = json.dumps(detail_parts) if detail_parts else None

    # The AuditLog model requires engagement_id (non-nullable FK).
    # For events not tied to an engagement, we log to the application
    # logger instead of the database.
    if engagement_id is None:
        logger.info(
            "Security event: action=%s actor=%s details=%s",
            action.value,
            actor,
            detail_str,
        )
        return None

    audit = AuditLog(
        engagement_id=engagement_id,
        action=action,
        actor=actor,
        details=detail_str,
    )
    session.add(audit)
    return audit


async def log_login(
    session: AsyncSession,
    actor: str,
    ip_address: str | None = None,
    success: bool = True,
) -> AuditLog | None:
    """Log a login event."""
    return await log_security_event(
        session=session,
        action=AuditAction.LOGIN,
        actor=actor,
        details={"success": success},
        ip_address=ip_address,
    )


async def log_permission_denied(
    session: AsyncSession,
    actor: str,
    permission: str,
    resource: str | None = None,
    engagement_id: UUID | None = None,
    ip_address: str | None = None,
) -> AuditLog | None:
    """Log a permission denied event."""
    return await log_security_event(
        session=session,
        action=AuditAction.PERMISSION_DENIED,
        actor=actor,
        engagement_id=engagement_id,
        details={"permission": permission},
        resource=resource,
        ip_address=ip_address,
    )


async def log_data_access(
    session: AsyncSession,
    actor: str,
    resource: str,
    engagement_id: UUID | None = None,
    ip_address: str | None = None,
) -> AuditLog | None:
    """Log a data access event."""
    return await log_security_event(
        session=session,
        action=AuditAction.DATA_ACCESS,
        actor=actor,
        engagement_id=engagement_id,
        resource=resource,
        ip_address=ip_address,
    )
