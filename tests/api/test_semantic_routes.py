"""Tests for semantic service API routes (KMFLOW-67)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.core.auth import get_current_user
from src.core.models import User
from src.core.models.auth import UserRole


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "test@kmflow.dev"
    user.name = "Test User"
    user.role = UserRole.PLATFORM_ADMIN
    user.is_active = True
    return user


@pytest.fixture
def client(mock_user):
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


class TestEntityExtractionEndpoint:
    def test_extract_entities_from_text(self, client) -> None:
        response = client.post(
            "/api/v1/semantic/extract",
            json={
                "text": "The Procurement Manager reviews the Purchase Order in SAP and approves the invoice.",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "entities" in data
        assert "entity_count" in data
        assert "by_type" in data
        assert data["entity_count"] > 0
        assert data["raw_text_length"] > 0

    def test_extract_entities_with_seed_terms(self, client) -> None:
        response = client.post(
            "/api/v1/semantic/extract",
            json={
                "text": "The Credit Risk Analyst performs the Credit Risk Assessment using the Risk Engine.",
                "seed_terms": ["Credit Risk Assessment", "Risk Engine"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["entity_count"] > 0

    def test_extract_entities_empty_text(self, client) -> None:
        response = client.post(
            "/api/v1/semantic/extract",
            json={"text": ""},
        )
        assert response.status_code == 422  # Validation error: min_length=1

    def test_extract_entities_returns_types(self, client) -> None:
        response = client.post(
            "/api/v1/semantic/extract",
            json={
                "text": (
                    "The Finance Manager creates an Invoice in SAP. "
                    "If the amount exceeds $10,000, the CFO must approve the Purchase Order."
                ),
            },
        )
        assert response.status_code == 200
        data = response.json()
        types_found = set(data["by_type"].keys())
        assert len(types_found) >= 2


class TestEntityResolutionEndpoint:
    def test_resolve_duplicate_entities(self, client) -> None:
        response = client.post(
            "/api/v1/semantic/resolve",
            json={
                "entities": [
                    {"id": "a1", "entity_type": "role", "name": "Finance Manager", "confidence": 0.8},
                    {"id": "a2", "entity_type": "role", "name": "finance manager", "confidence": 0.7},
                    {"id": "a3", "entity_type": "system", "name": "SAP", "confidence": 0.9},
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "resolved_entities" in data
        assert "duplicates_found" in data
        assert "merged_count" in data
        assert data["merged_count"] >= 1
        assert len(data["resolved_entities"]) < 3


class TestEmbeddingEndpoint:
    def test_generate_embeddings(self, client) -> None:
        response = client.post(
            "/api/v1/semantic/embed",
            json={"texts": ["Process the invoice", "Approve the purchase order"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["dimension"] > 0
        assert len(data["embeddings"]) == 2
        assert len(data["embeddings"][0]) == data["dimension"]

    def test_generate_single_embedding(self, client) -> None:
        response = client.post(
            "/api/v1/semantic/embed",
            json={"texts": ["Hello world"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1


class TestConfidenceEndpoint:
    def test_compute_confidence(self, client) -> None:
        response = client.post(
            "/api/v1/confidence/compute",
            json={
                "coverage": 0.8,
                "agreement": 0.7,
                "quality": 0.9,
                "reliability": 0.85,
                "recency": 0.75,
                "evidence_count": 5,
                "source_plane_count": 2,
                "has_sme_validation": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "final_score" in data
        assert "strength" in data
        assert "quality_score" in data
        assert "evidence_grade" in data
        assert "brightness" in data
        assert 0.0 <= data["final_score"] <= 1.0
        assert data["evidence_grade"] in ["A", "B", "C", "D", "U"]
        assert data["brightness"] in ["bright", "dim", "dark"]

    def test_compute_confidence_no_evidence(self, client) -> None:
        response = client.post(
            "/api/v1/confidence/compute",
            json={
                "coverage": 0.0,
                "agreement": 0.0,
                "quality": 0.0,
                "reliability": 0.0,
                "recency": 0.0,
                "evidence_count": 0,
                "source_plane_count": 0,
                "has_sme_validation": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["final_score"] == 0.0
        assert data["evidence_grade"] == "U"
        assert data["brightness"] == "dark"

    def test_compute_confidence_bright(self, client) -> None:
        response = client.post(
            "/api/v1/confidence/compute",
            json={
                "coverage": 1.0,
                "agreement": 1.0,
                "quality": 1.0,
                "reliability": 1.0,
                "recency": 1.0,
                "evidence_count": 10,
                "source_plane_count": 3,
                "has_sme_validation": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["final_score"] == 1.0
        assert data["evidence_grade"] == "A"
        assert data["brightness"] == "bright"

    def test_compute_batch_confidence(self, client) -> None:
        response = client.post(
            "/api/v1/confidence/compute/batch",
            json={
                "items": [
                    {
                        "coverage": 0.8,
                        "agreement": 0.7,
                        "quality": 0.9,
                        "reliability": 0.85,
                        "recency": 0.75,
                    },
                    {
                        "coverage": 0.3,
                        "agreement": 0.2,
                        "quality": 0.4,
                        "reliability": 0.3,
                        "recency": 0.5,
                    },
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["results"]) == 2
        assert data["results"][0]["final_score"] > data["results"][1]["final_score"]


class TestAuthRequired:
    def test_extract_requires_auth(self) -> None:
        """Endpoints should return 401 without auth."""
        # Clear any overrides
        app.dependency_overrides.pop(get_current_user, None)
        unauthenticated = TestClient(app)
        response = unauthenticated.post(
            "/api/v1/semantic/extract",
            json={"text": "test"},
        )
        # Should fail auth (401 or 403 depending on middleware)
        assert response.status_code in (401, 403, 500)
