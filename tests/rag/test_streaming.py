"""Tests for RAG streaming response."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.rag.copilot import CopilotOrchestrator


@pytest.fixture
def mock_retriever():
    """Mock hybrid retriever."""
    retriever = AsyncMock()
    retriever.retrieve = AsyncMock(return_value=[])
    return retriever


@pytest.fixture
def orchestrator(mock_retriever):
    """CopilotOrchestrator with mocked retriever."""
    return CopilotOrchestrator(retriever=mock_retriever)


class TestChatStreaming:
    """Tests for streaming response generation."""

    @pytest.mark.asyncio
    async def test_streaming_yields_done_marker(self, orchestrator) -> None:
        """Stream should always end with [DONE] marker."""
        session = AsyncMock()
        chunks = []
        async for chunk in orchestrator.chat_streaming(
            query="test question",
            engagement_id="eng-1",
            session=session,
        ):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert chunks[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_streaming_formats_as_sse(self, orchestrator) -> None:
        """All chunks should be SSE formatted."""
        session = AsyncMock()
        async for chunk in orchestrator.chat_streaming(
            query="test",
            engagement_id="eng-1",
            session=session,
        ):
            assert chunk.startswith("data: ")
            assert chunk.endswith("\n\n")

    @pytest.mark.asyncio
    async def test_streaming_stub_when_no_anthropic(self, orchestrator) -> None:
        """Should yield stub response when anthropic is not available."""
        session = AsyncMock()
        chunks = []
        async for chunk in orchestrator.chat_streaming(
            query="test",
            engagement_id="eng-1",
            session=session,
        ):
            chunks.append(chunk)

        # Should have at least the stub response + DONE marker
        assert len(chunks) >= 2
        # The stub response should mention unavailability
        assert "unavailable" in chunks[0] or "evidence" in chunks[0].lower()

    @pytest.mark.asyncio
    async def test_streaming_with_history(self, orchestrator) -> None:
        """Should accept conversation history."""
        session = AsyncMock()
        history = [
            {"role": "user", "content": "previous question"},
            {"role": "assistant", "content": "previous answer"},
        ]
        chunks = []
        async for chunk in orchestrator.chat_streaming(
            query="follow up",
            engagement_id="eng-1",
            session=session,
            history=history,
        ):
            chunks.append(chunk)

        assert len(chunks) >= 2

    @pytest.mark.asyncio
    async def test_streaming_with_query_type(self, orchestrator) -> None:
        """Should accept different query types."""
        session = AsyncMock()
        chunks = []
        async for chunk in orchestrator.chat_streaming(
            query="what gaps exist?",
            engagement_id="eng-1",
            session=session,
            query_type="gap_analysis",
        ):
            chunks.append(chunk)

        assert len(chunks) >= 2
