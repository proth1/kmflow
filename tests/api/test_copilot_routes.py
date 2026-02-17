"""Tests for copilot API routes (src/api/routes/copilot.py)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
class TestCopilotRoutes:
    async def test_chat_returns_answer(self, client, mock_db_session):
        mock_db_session.execute.return_value = MagicMock(
            fetchall=MagicMock(return_value=[])
        )

        response = await client.post(
            "/api/v1/copilot/chat",
            json={
                "engagement_id": "00000000-0000-0000-0000-000000000001",
                "query": "What processes exist?",
                "query_type": "general",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "citations" in data
        assert "query_type" in data
        assert "context_tokens_used" in data
        assert isinstance(data["answer"], str)
        assert isinstance(data["citations"], list)
        assert data["query_type"] == "general"

    async def test_chat_with_process_discovery_query(self, client, mock_db_session):
        mock_db_session.execute.return_value = MagicMock(
            fetchall=MagicMock(return_value=[])
        )

        response = await client.post(
            "/api/v1/copilot/chat",
            json={
                "engagement_id": "00000000-0000-0000-0000-000000000001",
                "query": "What are the steps in loan origination?",
                "query_type": "process_discovery",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert data["query_type"] == "process_discovery"

    async def test_chat_with_gap_analysis_query(self, client, mock_db_session):
        mock_db_session.execute.return_value = MagicMock(
            fetchall=MagicMock(return_value=[])
        )

        response = await client.post(
            "/api/v1/copilot/chat",
            json={
                "engagement_id": "00000000-0000-0000-0000-000000000001",
                "query": "What gaps exist between as-is and to-be?",
                "query_type": "gap_analysis",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert data["query_type"] == "gap_analysis"

    async def test_chat_with_invalid_query_type(self, client, mock_db_session):
        response = await client.post(
            "/api/v1/copilot/chat",
            json={
                "engagement_id": "00000000-0000-0000-0000-000000000001",
                "query": "What processes exist?",
                "query_type": "invalid_type",
            },
        )

        assert response.status_code == 422

    async def test_chat_with_missing_query(self, client, mock_db_session):
        response = await client.post(
            "/api/v1/copilot/chat",
            json={
                "engagement_id": "00000000-0000-0000-0000-000000000001",
                "query_type": "general",
            },
        )

        assert response.status_code == 422

    async def test_chat_with_invalid_engagement_id(self, client, mock_db_session):
        response = await client.post(
            "/api/v1/copilot/chat",
            json={
                "engagement_id": "not-a-uuid",
                "query": "What processes exist?",
                "query_type": "general",
            },
        )

        assert response.status_code == 422

    async def test_get_history_returns_empty(self, client, mock_db_session):
        engagement_id = "00000000-0000-0000-0000-000000000001"

        response = await client.get(f"/api/v1/copilot/history/{engagement_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["engagement_id"] == engagement_id
        assert data["messages"] == []
        assert data["total"] == 0

    async def test_get_history_with_invalid_engagement_id(self, client, mock_db_session):
        response = await client.get("/api/v1/copilot/history/not-a-uuid")

        assert response.status_code == 422
