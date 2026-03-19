"""Copilot request/response schemas.

Pydantic models for the RAG copilot API routes.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


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
