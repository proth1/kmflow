"""RAG copilot API routes.

Provides chat interface for evidence-based Q&A using hybrid retrieval
and Claude API generation. Persists chat history per engagement.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import CopilotMessage, User
from src.core.permissions import require_permission
from src.core.rate_limiter import copilot_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])


# -- Schemas ------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Request for copilot chat."""

    engagement_id: UUID
    query: str = Field(..., min_length=1, max_length=5000)
    query_type: str = Field(
        default="general", pattern="^(general|process_discovery|evidence_traceability|gap_analysis|regulatory)$"
    )
    history: list[dict[str, str]] | None = None


class CitationResponse(BaseModel):
    """A citation from retrieved evidence."""

    source_id: str
    source_type: str
    content_preview: str
    similarity_score: float


class ChatResponse(BaseModel):
    """Response from copilot chat."""

    answer: str
    citations: list[CitationResponse]
    query_type: str
    context_tokens_used: int


class ChatHistoryEntry(BaseModel):
    """A single entry in chat history."""

    role: str
    content: str
    query_type: str | None = None
    timestamp: str


class ChatHistoryResponse(BaseModel):
    """Response for chat history retrieval."""

    engagement_id: str
    messages: list[ChatHistoryEntry]
    total: int


# -- Dependency ---------------------------------------------------------------


async def get_session(request: Request):
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session


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
        )
    except Exception as e:
        logger.exception("Copilot chat failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Copilot error: {e}",
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

    async def event_generator():
        try:
            async for chunk in orchestrator.chat_streaming(
                query=payload.query,
                engagement_id=str(payload.engagement_id),
                session=session,
                query_type=payload.query_type,
                history=payload.history,
            ):
                yield chunk
        except Exception as e:
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
