"""RAG copilot API routes.

Provides chat interface for evidence-based Q&A using hybrid retrieval
and Claude API generation. Persists chat history per engagement.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.schemas.copilot import (
    ChatHistoryResponse,
    ChatRequest,
    ChatResponse,
)
from src.core.audit import log_audit
from src.core.models import AuditAction, CopilotMessage, User
from src.core.permissions import require_engagement_access, require_permission
from src.core.rate_limiter import copilot_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])


# -- Routes -------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
async def copilot_chat(
    payload: ChatRequest,
    request: Request,
    user: User = Depends(copilot_rate_limit),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Chat with the evidence copilot.

    Retrieves relevant evidence context and generates an AI response
    with citations to source documents. Rate-limited to 10 queries/min per user.
    """
    from src.rag.copilot import CopilotOrchestrator

    neo4j_driver = getattr(request.app.state, "neo4j_driver", None)
    orchestrator = CopilotOrchestrator(neo4j_driver=neo4j_driver)

    try:
        response = await orchestrator.chat(
            query=payload.query,
            engagement_id=str(payload.engagement_id),
            session=session,
            query_type=payload.query_type,
            history=payload.history,
            user_id=str(user.id),
        )
    except (ValueError, RuntimeError) as e:
        logger.exception("Copilot chat failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Copilot processing failed",
        ) from e

    citations = [
        {
            "source_id": c["source_id"],
            "source_type": c["source_type"],
            "content_preview": c["content_preview"],
            "similarity_score": c["similarity_score"],
        }
        for c in response.citations
    ]

    # Persist user query
    user_msg = CopilotMessage(
        engagement_id=payload.engagement_id,
        user_id=user.id,
        role="user",
        content=payload.query,
        query_type=payload.query_type,
    )
    session.add(user_msg)

    # Persist assistant response
    assistant_msg = CopilotMessage(
        engagement_id=payload.engagement_id,
        user_id=user.id,
        role="assistant",
        content=response.answer,
        query_type=payload.query_type,
        citations=citations,
        context_tokens_used=response.context_tokens_used,
    )
    session.add(assistant_msg)
    await log_audit(
        session,
        payload.engagement_id,
        AuditAction.DATA_ACCESS,
        f"Copilot query: {payload.query_type}",
        actor=str(user.id),
    )
    await session.commit()

    return {
        "answer": response.answer,
        "citations": citations,
        "query_type": response.query_type,
        "context_tokens_used": response.context_tokens_used,
    }


@router.get("/history/{engagement_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    engagement_id: UUID,
    user: User = Depends(require_permission("copilot:query")),
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Get chat history for an engagement with pagination."""
    # Count total messages
    count_result = await session.execute(
        select(func.count(CopilotMessage.id)).where(CopilotMessage.engagement_id == engagement_id)
    )
    total = count_result.scalar() or 0

    # Fetch paginated messages
    result = await session.execute(
        select(CopilotMessage)
        .where(CopilotMessage.engagement_id == engagement_id)
        .order_by(CopilotMessage.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    messages = list(result.scalars().all())

    return {
        "engagement_id": str(engagement_id),
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "query_type": msg.query_type,
                "timestamp": msg.created_at.isoformat(),
            }
            for msg in messages
        ],
        "total": total,
    }


@router.post("/chat/stream")
async def copilot_chat_stream(
    payload: ChatRequest,
    request: Request,
    user: User = Depends(copilot_rate_limit),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Stream a copilot response via Server-Sent Events.

    Returns an SSE stream where each event contains a text chunk.
    The stream ends with a "data: [DONE]" event.
    """
    from src.rag.copilot import CopilotOrchestrator

    neo4j_driver = getattr(request.app.state, "neo4j_driver", None)
    orchestrator = CopilotOrchestrator(neo4j_driver=neo4j_driver)

    await log_audit(
        session,
        payload.engagement_id,
        AuditAction.DATA_ACCESS,
        f"Copilot streaming query: {payload.query_type}",
        actor=str(user.id),
    )
    await session.commit()

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for chunk in orchestrator.chat_streaming(
                query=payload.query,
                engagement_id=str(payload.engagement_id),
                session=session,
                query_type=payload.query_type,
                history=payload.history,
                user_id=str(user.id),
            ):
                yield chunk
        except Exception as e:  # Intentionally broad: SSE generator must catch all errors to send DONE event
            logger.exception("Copilot streaming failed: %s", e)
            yield "data: Error: An error occurred. Please try again.\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# -- Feedback Schemas ---------------------------------------------------------


class FeedbackRequest(BaseModel):
    """Request to submit feedback on a copilot message."""

    copilot_message_id: UUID
    engagement_id: UUID
    rating: int = Field(..., ge=1, le=5)
    correction_text: str | None = None
    correction_sources: list[str] | None = None
    is_hallucination: bool = False


class FeedbackCreateResponse(BaseModel):
    """Response after submitting copilot feedback."""

    id: str
    created_at: str


class FeedbackSummaryResponse(BaseModel):
    """Aggregated copilot feedback statistics for an engagement."""

    total_feedback: int
    avg_rating: float
    thumbs_up: int
    thumbs_down: int
    hallucination_count: int
    correction_count: int


# -- Feedback Routes ----------------------------------------------------------


@router.post("/feedback", response_model=FeedbackCreateResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    payload: FeedbackRequest,
    user: User = Depends(copilot_rate_limit),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Submit feedback on a copilot message.

    Records a rating (1-5), optional correction text, optional correction
    sources, and whether the response was a hallucination. Returns the
    created feedback record ID.
    """
    from src.core.models.pipeline_quality import CopilotFeedback

    feedback = CopilotFeedback(
        copilot_message_id=payload.copilot_message_id,
        engagement_id=payload.engagement_id,
        user_id=user.id,
        rating=payload.rating,
        correction_text=payload.correction_text,
        correction_sources=payload.correction_sources,
        is_hallucination=payload.is_hallucination,
    )
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)

    return {"id": str(feedback.id), "created_at": feedback.created_at.isoformat()}


@router.get("/feedback/summary/{engagement_id}", response_model=FeedbackSummaryResponse)
async def get_feedback_summary(
    engagement_id: UUID,
    user: User = Depends(require_permission("copilot:query")),
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get aggregated copilot feedback statistics for an engagement."""
    from src.core.models.pipeline_quality import CopilotFeedback

    result = await session.execute(
        select(
            func.count(CopilotFeedback.id).label("total_feedback"),
            func.avg(CopilotFeedback.rating).label("avg_rating"),
            func.sum(func.cast(CopilotFeedback.rating >= 4, type_=func.count(CopilotFeedback.id).type)).label(
                "thumbs_up"
            ),
            func.sum(func.cast(CopilotFeedback.rating <= 2, type_=func.count(CopilotFeedback.id).type)).label(
                "thumbs_down"
            ),
            func.sum(func.cast(CopilotFeedback.is_hallucination, type_=func.count(CopilotFeedback.id).type)).label(
                "hallucination_count"
            ),
            func.sum(
                func.cast(
                    CopilotFeedback.correction_text.isnot(None),
                    type_=func.count(CopilotFeedback.id).type,
                )
            ).label("correction_count"),
        ).where(CopilotFeedback.engagement_id == engagement_id)
    )
    row = result.first()

    if row is None or row.total_feedback == 0:
        return {
            "total_feedback": 0,
            "avg_rating": 0.0,
            "thumbs_up": 0,
            "thumbs_down": 0,
            "hallucination_count": 0,
            "correction_count": 0,
        }

    return {
        "total_feedback": row.total_feedback or 0,
        "avg_rating": round(row.avg_rating or 0.0, 2),
        "thumbs_up": int(row.thumbs_up or 0),
        "thumbs_down": int(row.thumbs_down or 0),
        "hallucination_count": int(row.hallucination_count or 0),
        "correction_count": int(row.correction_count or 0),
    }
