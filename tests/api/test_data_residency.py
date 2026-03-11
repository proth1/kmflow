"""Tests for data residency enforcement middleware (KMFLOW-7)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.middleware.data_residency import check_data_residency, get_deployment_capabilities
from src.core.models.transfer import DataResidencyRestriction


class TestCheckDataResidency:
    @pytest.mark.asyncio
    async def test_no_restriction_allows_cloud(self) -> None:
        mock_engagement = MagicMock()
        mock_engagement.data_residency_restriction = "none"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_engagement
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await check_data_residency(uuid.uuid4(), session)
        assert result == DataResidencyRestriction.NONE

    @pytest.mark.asyncio
    async def test_eu_only_blocks_cloud_provider(self) -> None:
        mock_engagement = MagicMock()
        mock_engagement.data_residency_restriction = "eu_only"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_engagement
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        mock_llm = MagicMock()
        mock_llm.is_local = False
        mock_llm.provider_type.value = "anthropic"

        with patch("src.core.llm.get_llm_provider", return_value=mock_llm):
            with pytest.raises(HTTPException) as exc_info:
                await check_data_residency(uuid.uuid4(), session)
            assert exc_info.value.status_code == 403
            assert "data residency" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_eu_only_allows_local_provider(self) -> None:
        mock_engagement = MagicMock()
        mock_engagement.data_residency_restriction = "eu_only"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_engagement
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        mock_llm = MagicMock()
        mock_llm.is_local = True

        with patch("src.core.llm.get_llm_provider", return_value=mock_llm):
            result = await check_data_residency(uuid.uuid4(), session)
            assert result == DataResidencyRestriction.EU_ONLY

    @pytest.mark.asyncio
    async def test_not_found_raises_404(self) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await check_data_residency(uuid.uuid4(), session)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_custom_restriction_blocks_cloud(self) -> None:
        mock_engagement = MagicMock()
        mock_engagement.data_residency_restriction = "custom"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_engagement
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        mock_llm = MagicMock()
        mock_llm.is_local = False
        mock_llm.provider_type.value = "anthropic"

        with patch("src.core.llm.get_llm_provider", return_value=mock_llm):
            with pytest.raises(HTTPException) as exc_info:
                await check_data_residency(uuid.uuid4(), session)
            assert exc_info.value.status_code == 403


class TestGetDeploymentCapabilities:
    def test_with_anthropic_provider(self) -> None:
        mock_llm = MagicMock()
        mock_llm.provider_type.value = "anthropic"
        mock_llm.is_local = False

        with patch("src.core.llm.get_llm_provider", return_value=mock_llm):
            caps = get_deployment_capabilities()

        assert caps["llm_available"] is True
        assert caps["llm_provider"] == "anthropic"
        assert caps["llm_is_local"] is False
        assert caps["embeddings_local"] is True
        assert caps["copilot_enabled"] is True

    def test_with_stub_provider(self) -> None:
        mock_llm = MagicMock()
        mock_llm.provider_type.value = "stub"
        mock_llm.is_local = True

        with patch("src.core.llm.get_llm_provider", return_value=mock_llm):
            caps = get_deployment_capabilities()

        assert caps["llm_available"] is False
        assert caps["copilot_enabled"] is False
        assert caps["gap_rationale_enabled"] is False

    def test_with_ollama_provider(self) -> None:
        mock_llm = MagicMock()
        mock_llm.provider_type.value = "ollama"
        mock_llm.is_local = True

        with patch("src.core.llm.get_llm_provider", return_value=mock_llm):
            caps = get_deployment_capabilities()

        assert caps["llm_available"] is True
        assert caps["llm_is_local"] is True
        assert caps["copilot_enabled"] is True
