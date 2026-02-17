"""Tests for pattern library routes.

Tests the /api/v1/patterns endpoints for CRUD operations, search,
and access control.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.models import PatternAccessRule, PatternCategory, PatternLibraryEntry


class TestPatternRoutes:
    """Tests for pattern library CRUD routes."""

    @pytest.mark.asyncio
    async def test_create_pattern(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test creating a pattern in the library."""
        pattern_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        def refresh_side_effect(obj: Any) -> None:
            if isinstance(obj, PatternLibraryEntry):
                obj.id = pattern_id
                obj.usage_count = 0
                obj.effectiveness_score = 0.0
                obj.created_at = datetime.now(timezone.utc)

        mock_db_session.refresh.side_effect = refresh_side_effect

        response = await client.post(
            "/api/v1/patterns",
            json={
                "source_engagement_id": str(engagement_id),
                "category": "process_optimization",
                "title": "Test Pattern",
                "description": "A test pattern",
                "data": {"elements": []},
                "industry": "finance",
                "tags": ["test", "example"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Pattern"
        assert data["category"] == "process_optimization"

    @pytest.mark.asyncio
    async def test_list_patterns(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test listing patterns."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = await client.get("/api/v1/patterns")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_pattern(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test getting a pattern by ID."""
        pattern_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        mock_pattern = MagicMock(spec=PatternLibraryEntry)
        mock_pattern.id = pattern_id
        mock_pattern.source_engagement_id = engagement_id
        mock_pattern.category = PatternCategory.PROCESS_OPTIMIZATION
        mock_pattern.title = "Test Pattern"
        mock_pattern.description = "A test pattern"
        mock_pattern.anonymized_data = {}
        mock_pattern.industry = "finance"
        mock_pattern.tags = ["test"]
        mock_pattern.usage_count = 0
        mock_pattern.effectiveness_score = 0.0
        mock_pattern.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_pattern
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/patterns/{pattern_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(pattern_id)

    @pytest.mark.asyncio
    async def test_get_pattern_not_found(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test getting a pattern that does not exist."""
        pattern_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/patterns/{pattern_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_pattern(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test updating a pattern's title."""
        pattern_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        mock_pattern = MagicMock(spec=PatternLibraryEntry)
        mock_pattern.id = pattern_id
        mock_pattern.source_engagement_id = engagement_id
        mock_pattern.category = PatternCategory.PROCESS_OPTIMIZATION
        mock_pattern.title = "Old Title"
        mock_pattern.description = "A test pattern"
        mock_pattern.anonymized_data = {}
        mock_pattern.industry = "finance"
        mock_pattern.tags = ["test"]
        mock_pattern.usage_count = 0
        mock_pattern.effectiveness_score = 0.0
        mock_pattern.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_pattern
        mock_db_session.execute.return_value = mock_result

        response = await client.patch(
            f"/api/v1/patterns/{pattern_id}",
            json={"title": "New Title"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_delete_pattern(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test deleting a pattern."""
        pattern_id = uuid.uuid4()

        mock_pattern = MagicMock(spec=PatternLibraryEntry)
        mock_pattern.id = pattern_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_pattern
        mock_db_session.execute.return_value = mock_result

        response = await client.delete(f"/api/v1/patterns/{pattern_id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_pattern_not_found(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test deleting a pattern that does not exist."""
        pattern_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.delete(f"/api/v1/patterns/{pattern_id}")
        assert response.status_code == 404


class TestPatternSearch:
    """Tests for pattern search endpoint."""

    @pytest.mark.asyncio
    async def test_search_patterns(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test searching patterns with filters."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = await client.post(
            "/api/v1/patterns/search",
            json={
                "query": "test",
                "industry": "finance",
                "categories": ["process_optimization"],
                "limit": 10,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data


class TestPatternApply:
    """Tests for pattern apply endpoint."""

    @pytest.mark.asyncio
    async def test_apply_pattern(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test applying a pattern increments usage_count."""
        pattern_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        mock_pattern = MagicMock(spec=PatternLibraryEntry)
        mock_pattern.id = pattern_id
        mock_pattern.source_engagement_id = engagement_id
        mock_pattern.category = PatternCategory.PROCESS_OPTIMIZATION
        mock_pattern.title = "Test Pattern"
        mock_pattern.description = "A test pattern"
        mock_pattern.anonymized_data = {}
        mock_pattern.industry = "finance"
        mock_pattern.tags = ["test"]
        mock_pattern.usage_count = 5
        mock_pattern.effectiveness_score = 0.8
        mock_pattern.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_pattern
        mock_db_session.execute.return_value = mock_result

        response = await client.post(
            f"/api/v1/patterns/{pattern_id}/apply",
            json={"engagement_id": str(engagement_id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["usage_count"] == 6


class TestAccessRules:
    """Tests for pattern access rule routes."""

    @pytest.mark.asyncio
    async def test_create_access_rule(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test creating a pattern access rule."""
        rule_id = uuid.uuid4()
        pattern_id = uuid.uuid4()
        engagement_id = uuid.uuid4()

        def refresh_side_effect(obj: Any) -> None:
            if isinstance(obj, PatternAccessRule):
                obj.id = rule_id
                obj.granted_at = datetime.now(timezone.utc)

        mock_db_session.refresh.side_effect = refresh_side_effect

        response = await client.post(
            "/api/v1/patterns/access-rules",
            json={
                "pattern_id": str(pattern_id),
                "engagement_id": str(engagement_id),
                "granted_by": "test_user",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["pattern_id"] == str(pattern_id)
        assert data["engagement_id"] == str(engagement_id)
