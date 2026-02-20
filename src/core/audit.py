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


async def log_audit_event_async(
    method: str,
    path: str,
    user_id: str,
    status_code: int,
    engagement_id: str | None = None,
    duration_ms: float = 0.0,
) -> None:
    """Persist an HTTP audit event for compliance.

    The AuditLog database table requires a non-nullable engagement FK,
    so events not tied to a specific engagement are written to a
    structured machine-parseable log record instead of the database.
    Events that carry an engagement_id are also written to the log so
    that all HTTP audit events appear in the same log stream, enabling
    ingestion by SIEM tooling without requiring the caller to hold a
    database session.

    TODO: When a dedicated http_audit_events table (no FK constraint) is
    added, route all events to the database here.

    Args:
        method: HTTP method (POST, PUT, PATCH, DELETE, etc.).
        path: Request URL path.
        user_id: Authenticated user identifier, or "anonymous".
        status_code: HTTP response status code.
        engagement_id: Engagement UUID string extracted from the path, or None.
        duration_ms: Request processing time in milliseconds.
    """
    logger.info(
        "AUDIT_DB method=%s path=%s user=%s status=%d duration_ms=%.2f engagement=%s",
        method,
        path,
        user_id,
        status_code,
        duration_ms,
        engagement_id or "none",
    )


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
    # For events not tied to an engagement (e.g. LOGIN, PERMISSION_DENIED at
    # the auth layer), we emit a WARNING-level structured log record so the
    # event is never silently lost and SIEM tooling will capture it.
    # TODO: Add a security_events table without an engagement FK so these
    # events can be persisted to the database instead of the log stream.
    if engagement_id is None:
        logger.warning(
            "SECURITY_EVENT action=%s actor=%s details=%s",
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
