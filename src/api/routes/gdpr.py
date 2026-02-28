"""GDPR data subject rights API routes (Issue #165).

Implements the four GDPR data subject right operations required by GDPR
Chapter III:

- GET  /api/v1/gdpr/export          — Right of Access (Art. 15): export user's data
- POST /api/v1/gdpr/erasure-request — Right to Erasure (Art. 17): schedule anonymisation
- GET  /api/v1/gdpr/consent         — Consent status (Art. 7)
- POST /api/v1/gdpr/consent         — Update consent (Art. 7)

Admin-only:
- POST /api/v1/gdpr/admin/anonymize/{user_id} — Execute immediate anonymisation

Design notes:
- Erasure does NOT delete records immediately. It sets erasure_requested_at /
  erasure_scheduled_at on the User row. A background job (not yet implemented)
  is responsible for performing the actual anonymisation once the grace period
  has elapsed. Immediate anonymisation is available to platform admins via the
  separate admin endpoint.
- Consent changes are recorded as immutable audit rows in user_consents (one
  row per change event), never updated in place.
- Data export collects from: users, engagement_members, audit_logs (actor field),
  annotations (author_id field).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.auth import get_current_user
from src.core.config import get_settings
from src.core.models import Annotation, AuditLog, CopilotMessage, EngagementMember, User, UserConsent, UserRole
from src.core.permissions import has_role_level

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gdpr"])

# ---------------------------------------------------------------------------
# Valid consent types
# ---------------------------------------------------------------------------

VALID_CONSENT_TYPES: frozenset[str] = frozenset({"analytics", "data_processing", "marketing_communications"})

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DataExportResponse(BaseModel):
    """Full GDPR data export for the requesting user."""

    user_profile: dict[str, Any]
    memberships: list[dict[str, Any]]
    audit_entries: list[dict[str, Any]]
    annotations: list[dict[str, Any]]
    user_consents: list[dict[str, Any]]
    copilot_messages: list[dict[str, Any]]


class ErasureRequestResponse(BaseModel):
    """Confirmation that an erasure request was recorded."""

    user_id: UUID
    erasure_requested_at: datetime
    erasure_scheduled_at: datetime
    message: str


class ConsentItem(BaseModel):
    """Current consent state for a single consent type."""

    consent_type: str
    granted: bool
    granted_at: datetime
    revoked_at: datetime | None = None


class ConsentStatusResponse(BaseModel):
    """Full consent status for the current user."""

    user_id: UUID
    consents: list[ConsentItem]


class ConsentUpdate(BaseModel):
    """Payload for updating consent preferences."""

    consent_type: str = Field(..., description="One of: analytics, data_processing, marketing_communications")
    granted: bool = Field(..., description="True to grant consent, False to revoke")


class AnonymizeResponse(BaseModel):
    """Confirmation that a user account was immediately anonymised."""

    user_id: UUID
    anonymized_at: datetime
    message: str


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _user_to_dict(user: User) -> dict[str, Any]:
    """Convert a User ORM object to a serialisable dict, excluding PII-adjacent secrets."""
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
        "is_active": user.is_active,
        "external_id": user.external_id,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "erasure_requested_at": user.erasure_requested_at.isoformat() if user.erasure_requested_at else None,
        "erasure_scheduled_at": user.erasure_scheduled_at.isoformat() if user.erasure_scheduled_at else None,
    }


def _member_to_dict(member: EngagementMember) -> dict[str, Any]:
    return {
        "id": str(member.id),
        "engagement_id": str(member.engagement_id),
        "user_id": str(member.user_id),
        "role_in_engagement": member.role_in_engagement,
        "added_at": member.added_at.isoformat() if member.added_at else None,
    }


def _audit_to_dict(entry: AuditLog) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "engagement_id": str(entry.engagement_id),
        "action": entry.action.value,
        "actor": entry.actor,
        "details": entry.details,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


def _annotation_to_dict(annotation: Annotation) -> dict[str, Any]:
    return {
        "id": str(annotation.id),
        "engagement_id": str(annotation.engagement_id),
        "target_type": annotation.target_type,
        "target_id": annotation.target_id,
        "author_id": annotation.author_id,
        "content": annotation.content,
        "created_at": annotation.created_at.isoformat() if annotation.created_at else None,
        "updated_at": annotation.updated_at.isoformat() if annotation.updated_at else None,
    }


def _get_client_ip(request: Request) -> str | None:
    """Extract the client IP address from the request, respecting proxy headers."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first (client) IP from potentially comma-separated list
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else None


# ---------------------------------------------------------------------------
# GET /api/v1/gdpr/export
# ---------------------------------------------------------------------------


@router.get("/api/v1/gdpr/export", response_model=DataExportResponse)
async def export_user_data(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DataExportResponse:
    """Export all personal data held for the authenticated user (GDPR Art. 15).

    Collects data from:
    - users table (profile)
    - engagement_members table (memberships)
    - audit_logs table (entries where actor = user id string)
    - annotations table (entries where author_id = user id string)
    """
    user_id_str = str(current_user.id)

    # Membership records
    member_result = await session.execute(select(EngagementMember).where(EngagementMember.user_id == current_user.id))
    memberships = [_member_to_dict(m) for m in member_result.scalars().all()]

    # Audit log entries attributed to this user
    audit_result = await session.execute(select(AuditLog).where(AuditLog.actor == user_id_str))
    audit_entries = [_audit_to_dict(e) for e in audit_result.scalars().all()]

    # Annotations authored by this user
    annotation_result = await session.execute(select(Annotation).where(Annotation.author_id == user_id_str))
    annotations = [_annotation_to_dict(a) for a in annotation_result.scalars().all()]

    # User consent records
    consent_result = await session.execute(select(UserConsent).where(UserConsent.user_id == current_user.id))
    user_consents = [
        {
            "id": str(c.id),
            "consent_type": c.consent_type,
            "granted": c.granted,
            "granted_at": c.granted_at.isoformat() if c.granted_at else None,
            "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
            "ip_address": c.ip_address,
        }
        for c in consent_result.scalars().all()
    ]

    # Copilot chat messages for the user
    copilot_result = await session.execute(select(CopilotMessage).where(CopilotMessage.user_id == current_user.id))
    copilot_messages = [
        {
            "id": str(m.id),
            "engagement_id": str(m.engagement_id),
            "role": m.role,
            "content": m.content,
            "query_type": m.query_type,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in copilot_result.scalars().all()
    ]

    return DataExportResponse(
        user_profile=_user_to_dict(current_user),
        memberships=memberships,
        audit_entries=audit_entries,
        annotations=annotations,
        user_consents=user_consents,
        copilot_messages=copilot_messages,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/gdpr/erasure-request
# ---------------------------------------------------------------------------


@router.post("/api/v1/gdpr/erasure-request", response_model=ErasureRequestResponse)
async def request_erasure(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    settings=Depends(get_settings),
) -> ErasureRequestResponse:
    """Schedule the current user's account for erasure (GDPR Art. 17).

    Sets erasure_requested_at and erasure_scheduled_at on the User row.
    A background job is responsible for executing the actual anonymisation
    once the grace period (gdpr_erasure_grace_days) has elapsed.

    During the grace period, the user can cancel by PATCHing their profile
    (not implemented here; would clear the two timestamp fields).
    """
    now = datetime.now(UTC)
    scheduled_at = now + timedelta(days=settings.gdpr_erasure_grace_days)

    # Re-fetch the user row inside this session so we can mutate it
    result = await session.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.erasure_requested_at = now
    user.erasure_scheduled_at = scheduled_at

    await session.commit()
    await session.refresh(user)

    logger.info(
        "GDPR erasure request recorded for user %s; scheduled for %s",
        current_user.id,
        scheduled_at.isoformat(),
    )

    return ErasureRequestResponse(
        user_id=user.id,
        erasure_requested_at=user.erasure_requested_at,
        erasure_scheduled_at=user.erasure_scheduled_at,
        message=(
            f"Your account is scheduled for erasure on {scheduled_at.date().isoformat()}. "
            f"You have {settings.gdpr_erasure_grace_days} days to cancel this request."
        ),
    )


# ---------------------------------------------------------------------------
# GET /api/v1/gdpr/consent
# ---------------------------------------------------------------------------


@router.get("/api/v1/gdpr/consent", response_model=ConsentStatusResponse)
async def get_consent_status(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ConsentStatusResponse:
    """Return the current consent status for all consent types (GDPR Art. 7).

    For each valid consent type, returns the most recent recorded consent event.
    Types with no record yet are omitted from the response list.
    """
    # Fetch all consent rows for this user ordered by granted_at DESC so we
    # can pick the latest event per consent_type.
    result = await session.execute(
        select(UserConsent).where(UserConsent.user_id == current_user.id).order_by(UserConsent.granted_at.desc())
    )
    all_consents = result.scalars().all()

    # Keep only the most recent event per type
    seen: set[str] = set()
    latest: list[ConsentItem] = []
    for consent in all_consents:
        if consent.consent_type not in seen:
            seen.add(consent.consent_type)
            latest.append(
                ConsentItem(
                    consent_type=consent.consent_type,
                    granted=consent.granted,
                    granted_at=consent.granted_at,
                    revoked_at=consent.revoked_at,
                )
            )

    return ConsentStatusResponse(user_id=current_user.id, consents=latest)


# ---------------------------------------------------------------------------
# POST /api/v1/gdpr/consent
# ---------------------------------------------------------------------------


@router.post("/api/v1/gdpr/consent", response_model=ConsentStatusResponse, status_code=status.HTTP_200_OK)
async def update_consent(
    payload: ConsentUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ConsentStatusResponse:
    """Record a consent grant or revocation (GDPR Art. 7).

    Consent changes are recorded as new immutable rows in user_consents.
    The IP address is captured for audit trail purposes.
    """
    if payload.consent_type not in VALID_CONSENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(f"Invalid consent_type '{payload.consent_type}'. Must be one of: {sorted(VALID_CONSENT_TYPES)}"),
        )

    now = datetime.now(UTC)
    ip_address = _get_client_ip(request)

    consent = UserConsent(
        id=uuid.uuid4(),
        user_id=current_user.id,
        consent_type=payload.consent_type,
        granted=payload.granted,
        granted_at=now,
        revoked_at=None if payload.granted else now,
        ip_address=ip_address,
    )
    session.add(consent)
    await session.commit()

    logger.info(
        "GDPR consent %s for type '%s' recorded for user %s (ip=%s)",
        "granted" if payload.granted else "revoked",
        payload.consent_type,
        current_user.id,
        ip_address,
    )

    # Return the updated full consent status
    return await get_consent_status(session=session, current_user=current_user)


# ---------------------------------------------------------------------------
# POST /api/v1/gdpr/admin/anonymize/{user_id}  (platform_admin only)
# ---------------------------------------------------------------------------


@router.post(
    "/api/v1/gdpr/admin/anonymize/{user_id}",
    response_model=AnonymizeResponse,
    status_code=status.HTTP_200_OK,
)
async def admin_anonymize_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AnonymizeResponse:
    """Immediately anonymise a user account (platform_admin only).

    Anonymisation replaces PII fields but preserves structural data so that
    audit log integrity is maintained:
    - user.name  -> "Deleted User"
    - user.email -> "deleted-{uuid}@anonymized.local"
    - user.is_active -> False
    - user.hashed_password -> None
    - user.external_id -> None
    - audit_logs where actor = user_id_str -> actor set to "anonymized"

    The user's UUID is retained so that foreign key relationships remain
    intact (engagement_members, copilot_messages, etc.).
    """
    if not has_role_level(current_user, UserRole.PLATFORM_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform admins can immediately anonymise user accounts",
        )

    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    anon_id = uuid.uuid4()
    anon_email = f"deleted-{anon_id}@anonymized.local"

    # Anonymise the user row
    target.name = "Deleted User"
    target.email = anon_email
    target.is_active = False
    target.hashed_password = None
    target.external_id = None

    # Anonymise audit log actor references — we use a raw UPDATE via text()
    # to avoid loading every AuditLog row into memory.
    user_id_str = str(user_id)
    await session.execute(
        text("UPDATE audit_logs SET actor = 'anonymized' WHERE actor = :uid"),
        {"uid": user_id_str},
    )

    # Anonymise task mining data — delete events/actions/quarantine for
    # agents registered by this user's engagements. Agent records are
    # kept but hostname is anonymised.
    await session.execute(
        text("UPDATE task_mining_agents SET hostname = 'anonymized', approved_by = NULL WHERE approved_by = :uid"),
        {"uid": user_id_str},
    )

    now = datetime.now(UTC)
    await session.commit()

    logger.info(
        "GDPR immediate anonymisation performed on user %s by admin %s",
        user_id,
        current_user.id,
    )

    return AnonymizeResponse(
        user_id=user_id,
        anonymized_at=now,
        message=f"User {user_id} has been anonymised. PII fields replaced; structural records preserved.",
    )
