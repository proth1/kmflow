"""Token-based client evidence intake routes.

These endpoints do NOT require bearer token authentication.
Clients use a time-limited intake token to submit evidence files
for shelf data requests.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import get_session
from src.core.models import (
    ShelfDataRequest,
    ShelfDataRequestToken,
    ShelfRequestItemStatus,
    ShelfRequestStatus,
    UploadFileStatus,
    User,
)
from src.core.permissions import require_permission
from src.evidence.intake import (
    DEFAULT_TOKEN_EXPIRY_DAYS,
    generate_intake_token,
    match_filename_to_items,
    validate_intake_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["intake"])


# -- Schemas ------------------------------------------------------------------


class GenerateIntakeLinkRequest(BaseModel):
    """Request to generate an intake link."""

    expiry_days: int = Field(default=DEFAULT_TOKEN_EXPIRY_DAYS, ge=1, le=365)


class GenerateIntakeLinkResponse(BaseModel):
    """Response with the generated intake link."""

    token: UUID
    intake_url: str
    expires_at: str
    expiry_days: int


class UploadedFileResult(BaseModel):
    """Result for a single uploaded file."""

    filename: str
    status: UploadFileStatus
    matched_item_id: UUID | None = None
    matched_item_name: str | None = None
    error: str | None = None


class IntakeUploadResponse(BaseModel):
    """Response from the intake upload endpoint."""

    token: UUID
    request_id: UUID
    total_files: int
    matched_count: int
    unmatched_count: int
    failed_count: int
    files: list[UploadedFileResult]


class IntakeProgressResponse(BaseModel):
    """Progress for all files in an intake upload."""

    token: UUID
    request_id: UUID
    files: list[UploadedFileResult]


# -- Token generation (authenticated) ----------------------------------------


@router.post(
    "/api/v1/shelf-requests/{request_id}/generate-intake-link",
    response_model=GenerateIntakeLinkResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["shelf-requests"],
)
async def generate_intake_link(
    request_id: UUID,
    payload: GenerateIntakeLinkRequest | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Generate a time-limited intake link for client evidence submission.

    The returned URL can be shared with clients without requiring authentication.
    """
    # Verify request exists and is OPEN
    result = await session.execute(select(ShelfDataRequest).where(ShelfDataRequest.id == request_id))
    shelf_request = result.scalar_one_or_none()
    if not shelf_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shelf data request {request_id} not found",
        )

    if shelf_request.status != ShelfRequestStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Shelf data request must be OPEN to generate intake link (current: {shelf_request.status})",
        )

    expiry_days = payload.expiry_days if payload else DEFAULT_TOKEN_EXPIRY_DAYS
    created_by = str(user.id) if hasattr(user, "id") else None

    token_record = generate_intake_token(
        request_id=request_id,
        created_by=created_by,
        expiry_days=expiry_days,
    )
    session.add(token_record)
    await session.commit()
    await session.refresh(token_record)

    intake_url = f"/api/v1/intake/{token_record.token}"

    return {
        "token": token_record.token,
        "intake_url": intake_url,
        "expires_at": token_record.expires_at.isoformat(),
        "expiry_days": expiry_days,
    }


# -- Token-based intake (NO authentication) ----------------------------------


async def _get_valid_token(
    token: UUID,
    session: AsyncSession,
) -> ShelfDataRequestToken:
    """Fetch and validate an intake token. Raises HTTPException if invalid."""
    result = await session.execute(
        select(ShelfDataRequestToken)
        .options(selectinload(ShelfDataRequestToken.request).selectinload(ShelfDataRequest.items))
        .where(ShelfDataRequestToken.token == token)
    )
    token_record = result.scalar_one_or_none()

    error = validate_intake_token(token_record)
    if error:
        if token_record and token_record.is_expired:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=error,
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error,
        )

    assert token_record is not None  # validate_intake_token guarantees this
    return token_record


@router.post(
    "/api/v1/intake/{token}",
    response_model=IntakeUploadResponse,
)
async def submit_intake_files(
    token: UUID,
    filenames: list[str] = Query(..., description="List of filenames being uploaded"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Submit evidence files via intake token (no authentication required).

    Accepts a list of filenames and auto-matches them to request items.
    Matched items transition to RECEIVED status. Unmatched files are
    flagged for manual analyst assignment.
    """
    token_record = await _get_valid_token(token, session)
    shelf_request = token_record.request

    # Build item name list for matching
    item_names: list[tuple[str, str]] = [
        (str(item.id), item.item_name)
        for item in shelf_request.items
        if item.status in (ShelfRequestItemStatus.PENDING, ShelfRequestItemStatus.REQUESTED)
    ]

    results: list[dict[str, Any]] = []
    matched_count = 0
    unmatched_count = 0
    failed_count = 0
    matched_item_ids: set[str] = set()

    for filename in filenames:
        # Auto-match
        matched_id, score = match_filename_to_items(
            filename,
            [(iid, iname) for iid, iname in item_names if iid not in matched_item_ids],
        )

        if matched_id:
            # Find the item and update status
            matched_item = next(
                (item for item in shelf_request.items if str(item.id) == matched_id),
                None,
            )
            if matched_item:
                matched_item.status = ShelfRequestItemStatus.RECEIVED
                matched_item_ids.add(matched_id)
                matched_count += 1
                results.append(
                    {
                        "filename": filename,
                        "status": UploadFileStatus.COMPLETE,
                        "matched_item_id": matched_item.id,
                        "matched_item_name": matched_item.item_name,
                        "error": None,
                    }
                )
            else:
                unmatched_count += 1
                results.append(
                    {
                        "filename": filename,
                        "status": UploadFileStatus.COMPLETE,
                        "matched_item_id": None,
                        "matched_item_name": None,
                        "error": None,
                    }
                )
        else:
            unmatched_count += 1
            results.append(
                {
                    "filename": filename,
                    "status": UploadFileStatus.COMPLETE,
                    "matched_item_id": None,
                    "matched_item_name": None,
                    "error": None,
                }
            )

    # Increment used_count
    token_record.used_count += 1
    await session.commit()

    return {
        "token": token_record.token,
        "request_id": shelf_request.id,
        "total_files": len(filenames),
        "matched_count": matched_count,
        "unmatched_count": unmatched_count,
        "failed_count": failed_count,
        "files": results,
    }


@router.get(
    "/api/v1/intake/{token}/progress",
    response_model=IntakeProgressResponse,
)
async def get_intake_progress(
    token: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get progress for files uploaded via an intake token (no auth required)."""
    token_record = await _get_valid_token(token, session)
    shelf_request = token_record.request

    files: list[dict[str, Any]] = []
    for item in shelf_request.items:
        if item.status == ShelfRequestItemStatus.RECEIVED:
            files.append(
                {
                    "filename": item.item_name,
                    "status": UploadFileStatus.COMPLETE,
                    "matched_item_id": item.id,
                    "matched_item_name": item.item_name,
                    "error": None,
                }
            )
        else:
            files.append(
                {
                    "filename": item.item_name,
                    "status": UploadFileStatus.QUEUED,
                    "matched_item_id": None,
                    "matched_item_name": None,
                    "error": None,
                }
            )

    return {
        "token": token_record.token,
        "request_id": shelf_request.id,
        "files": files,
    }
