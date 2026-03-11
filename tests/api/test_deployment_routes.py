"""Tests for deployment capabilities API routes (KMFLOW-7)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestCapabilitiesEndpoint:
    def test_returns_capabilities(self, client: TestClient) -> None:
        mock_llm = MagicMock()
        mock_llm.provider_type.value = "anthropic"
        mock_llm.is_local = False

        with patch("src.core.llm.get_llm_provider", return_value=mock_llm):
            response = client.get("/api/v1/deployment/capabilities")

        assert response.status_code == 200
        data = response.json()
        assert "llm_available" in data
        assert "llm_provider" in data
        assert "llm_is_local" in data
        assert "embeddings_local" in data
        assert "copilot_enabled" in data

    def test_stub_provider_disables_features(self, client: TestClient) -> None:
        mock_llm = MagicMock()
        mock_llm.provider_type.value = "stub"
        mock_llm.is_local = True

        with patch("src.core.llm.get_llm_provider", return_value=mock_llm):
            response = client.get("/api/v1/deployment/capabilities")

        assert response.status_code == 200
        data = response.json()
        assert data["llm_available"] is False
        assert data["copilot_enabled"] is False
        assert data["scenario_suggestions_enabled"] is False

    def test_ollama_provider_is_local(self, client: TestClient) -> None:
        mock_llm = MagicMock()
        mock_llm.provider_type.value = "ollama"
        mock_llm.is_local = True

        with patch("src.core.llm.get_llm_provider", return_value=mock_llm):
            response = client.get("/api/v1/deployment/capabilities")

        assert response.status_code == 200
        data = response.json()
        assert data["llm_available"] is True
        assert data["llm_is_local"] is True
        assert data["copilot_enabled"] is True
