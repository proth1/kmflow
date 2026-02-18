"""Tests for lineage API route schemas and structure.

Tests validate the Pydantic response models and route definitions.
Full HTTP integration tests require a running database.
"""

from __future__ import annotations

import uuid

from src.api.routes.lineage import LineageChainResponse, LineageResponse


class TestLineageResponseSchema:
    """Test lineage response schema validation."""

    def test_valid_lineage_response(self) -> None:
        data = {
            "id": str(uuid.uuid4()),
            "evidence_item_id": str(uuid.uuid4()),
            "source_system": "direct_upload",
            "source_url": None,
            "source_identifier": None,
            "transformation_chain": [
                {"step": "ingestion", "action": "uploaded"},
            ],
            "version": 1,
            "version_hash": "abc123",
            "parent_version_id": None,
            "refresh_schedule": None,
            "last_refreshed_at": None,
            "created_at": "2026-02-18T00:00:00Z",
        }
        resp = LineageResponse(**data)
        assert resp.source_system == "direct_upload"
        assert resp.version == 1

    def test_valid_chain_response(self) -> None:
        ev_id = uuid.uuid4()
        data = {
            "evidence_item_id": str(ev_id),
            "evidence_name": "test.pdf",
            "source_system": "salesforce",
            "total_versions": 1,
            "lineage": [
                {
                    "id": str(uuid.uuid4()),
                    "evidence_item_id": str(ev_id),
                    "source_system": "salesforce",
                    "source_url": "https://sf.com/file",
                    "source_identifier": "SF-123",
                    "transformation_chain": [],
                    "version": 1,
                    "version_hash": "def456",
                    "parent_version_id": None,
                    "refresh_schedule": None,
                    "last_refreshed_at": None,
                    "created_at": "2026-02-18T00:00:00Z",
                },
            ],
        }
        resp = LineageChainResponse(**data)
        assert resp.evidence_name == "test.pdf"
        assert resp.total_versions == 1
        assert len(resp.lineage) == 1

    def test_chain_response_empty_lineage(self) -> None:
        data = {
            "evidence_item_id": str(uuid.uuid4()),
            "evidence_name": "doc.docx",
            "source_system": None,
            "total_versions": 0,
            "lineage": [],
        }
        resp = LineageChainResponse(**data)
        assert resp.total_versions == 0
        assert resp.lineage == []


class TestLineageRouteRegistration:
    """Verify lineage routes are registered in the app."""

    def test_lineage_router_exists(self) -> None:
        from src.api.routes.lineage import router

        routes = [r.path for r in router.routes]
        assert any("/lineage" in r for r in routes)
