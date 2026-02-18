"""RAG copilot orchestrator for evidence-based Q&A."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.rag.embeddings import EmbeddingService
from src.rag.prompts import SYSTEM_PROMPT, build_context_string, get_prompt_template
from src.rag.retrieval import HybridRetriever, RetrievalResult

logger = logging.getLogger(__name__)


@dataclass
class CopilotMessage:
    """A single message in a copilot conversation."""

    role: str  # "user" or "assistant"
    content: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


@dataclass
class CopilotResponse:
    """Response from the copilot."""

    answer: str
    citations: list[dict[str, Any]]
    query_type: str
    context_tokens_used: int
    retrieval_results: list[RetrievalResult]


class CopilotOrchestrator:
    """Orchestrates the RAG pipeline: retrieve -> build prompt -> generate response."""

    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        embedding_service: EmbeddingService | None = None,
        neo4j_driver: Any = None,
    ):
        self.embedding_service = embedding_service or EmbeddingService()
        self.retriever = retriever or HybridRetriever(
            embedding_service=self.embedding_service,
            neo4j_driver=neo4j_driver,
        )
        self.settings = get_settings()

    async def chat(
        self,
        query: str,
        engagement_id: str,
        session: AsyncSession,
        query_type: str = "general",
        history: list[dict[str, Any]] | None = None,
    ) -> CopilotResponse:
        """Process a copilot query through the RAG pipeline."""
        # 1. Retrieve relevant context
        retrieval_results = await self.retriever.retrieve(
            query=query,
            session=session,
            engagement_id=engagement_id,
            top_k=10,
        )

        # 2. Build context string from results
        contexts = [
            {
                "content": r.content,
                "source_id": r.source_id,
                "source_type": r.source_type,
                "similarity_score": r.similarity_score,
            }
            for r in retrieval_results
        ]
        context_string = build_context_string(contexts)

        # 3. Build prompt from template
        template = get_prompt_template(query_type)
        user_prompt = template.format(
            engagement_id=engagement_id,
            context=context_string,
            query=query,
        )

        # 4. Generate response (using Anthropic API if available, else stub)
        answer = await self._generate_response(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            history=history,
        )

        # 5. Extract citations from retrieval results
        citations = [
            {
                "source_id": r.source_id,
                "source_type": r.source_type,
                "content_preview": r.content[:200],
                "similarity_score": r.similarity_score,
                **r.metadata,
            }
            for r in retrieval_results
        ]

        return CopilotResponse(
            answer=answer,
            citations=citations,
            query_type=query_type,
            context_tokens_used=len(context_string.split()),
            retrieval_results=retrieval_results,
        )

    async def _generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate a response using Claude API or fallback."""
        try:
            import anthropic

            client = anthropic.AsyncAnthropic()
            messages = []

            # Add conversation history
            if history:
                for msg in history[-5:]:  # Keep last 5 messages for context
                    messages.append({"role": msg["role"], "content": msg["content"]})

            messages.append({"role": "user", "content": user_prompt})

            response = await client.messages.create(
                model=self.settings.copilot_model,
                max_tokens=self.settings.copilot_max_response_tokens,
                system=system_prompt,
                messages=messages,  # type: ignore[arg-type]
            )
            return response.content[0].text  # type: ignore[union-attr]

        except ImportError:
            logger.warning("anthropic package not installed, using stub response")
            return self._stub_response(user_prompt)
        except Exception as e:
            logger.error("Claude API call failed: %s", e)
            return self._stub_response(user_prompt)

    async def chat_streaming(
        self,
        query: str,
        engagement_id: str,
        session: AsyncSession,
        query_type: str = "general",
        history: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Process a copilot query and stream the response token by token.

        Yields SSE-formatted text chunks for streaming to the client.

        Args:
            query: The user's question.
            engagement_id: Engagement scope.
            session: Database session for retrieval.
            query_type: Type of query for prompt selection.
            history: Previous conversation messages.

        Yields:
            SSE-formatted strings: "data: {text}\n\n" for each chunk,
            "data: [DONE]\n\n" when complete.
        """
        # 1. Retrieve relevant context
        retrieval_results = await self.retriever.retrieve(
            query=query,
            session=session,
            engagement_id=engagement_id,
            top_k=10,
        )

        # 2. Build context and prompt
        contexts = [
            {
                "content": r.content,
                "source_id": r.source_id,
                "source_type": r.source_type,
                "similarity_score": r.similarity_score,
            }
            for r in retrieval_results
        ]
        context_string = build_context_string(contexts)
        template = get_prompt_template(query_type)
        user_prompt = template.format(
            engagement_id=engagement_id,
            context=context_string,
            query=query,
        )

        # 3. Stream response
        try:
            import anthropic

            client = anthropic.AsyncAnthropic()
            messages: list[dict[str, str]] = []

            if history:
                for msg in history[-5:]:
                    messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": user_prompt})

            async with client.messages.stream(
                model=self.settings.copilot_model,
                max_tokens=self.settings.copilot_max_response_tokens,
                system=SYSTEM_PROMPT,
                messages=messages,  # type: ignore[arg-type]
            ) as stream:
                async for text_chunk in stream.text_stream:
                    yield f"data: {text_chunk}\n\n"

        except ImportError:
            logger.warning("anthropic package not installed, yielding stub response")
            yield f"data: {self._stub_response(user_prompt)}\n\n"
        except Exception as e:
            logger.error("Claude streaming failed: %s", e)
            yield f"data: {self._stub_response(user_prompt)}\n\n"

        yield "data: [DONE]\n\n"

    def _stub_response(self, prompt: str) -> str:
        """Fallback stub response when Claude API is unavailable."""
        return (
            "I found relevant evidence for your query but the AI generation "
            "service is currently unavailable. Please review the cited sources "
            "directly for the information you need."
        )
