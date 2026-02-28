"""Tests for PEP (Policy Enforcement Point) middleware.

Covers permit/deny decisions and obligation enforcement via the middleware
layer, mocking the PDP service to avoid database dependencies.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from src.api.middleware.pep import (
    PEPMiddleware,
    _is_protected,
    _method_to_operation,
    _extract_engagement_id,
)
from src.core.models.pdp import PDPDecisionType, ObligationType


# ---------------------------------------------------------------------------
# Unit tests: helpers
# ---------------------------------------------------------------------------


def test_is_protected_evidence_path() -> None:
    assert _is_protected("/api/v1/evidence/123") is True


def test_is_protected_health_excluded() -> None:
    assert _is_protected("/api/v1/health") is False


def test_is_protected_pdp_excluded() -> None:
    assert _is_protected("/api/v1/pdp/evaluate") is False


def test_is_protected_unregistered_path() -> None:
    assert _is_protected("/api/v1/auth/login") is False


def test_method_to_operation_get() -> None:
    assert _method_to_operation("GET") == "read"


def test_method_to_operation_delete() -> None:
    assert _method_to_operation("DELETE") == "delete"


def test_method_to_operation_post() -> None:
    assert _method_to_operation("POST") == "write"


def test_extract_engagement_id_present() -> None:
    uid = str(uuid.uuid4())
    path = f"/api/v1/engagements/{uid}/evidence"
    result = _extract_engagement_id(path)
    assert result == uid


def test_extract_engagement_id_absent() -> None:
    assert _extract_engagement_id("/api/v1/evidence/123") is None


def test_extract_engagement_id_invalid_uuid() -> None:
    assert _extract_engagement_id("/api/v1/engagements/not-a-uuid/items") is None


# ---------------------------------------------------------------------------
# Integration tests via ASGI
# ---------------------------------------------------------------------------


def _make_permit_result(obligations: list[dict] | None = None) -> dict[str, Any]:
    return {
        "decision": PDPDecisionType.PERMIT,
        "obligations": obligations or [],
        "reason": None,
        "audit_id": str(uuid.uuid4()),
    }


def _make_deny_result(reason: str = "insufficient_clearance") -> dict[str, Any]:
    return {
        "decision": PDPDecisionType.DENY,
        "obligations": [],
        "reason": reason,
        "audit_id": str(uuid.uuid4()),
    }


async def _evidence_endpoint(request: Request) -> JSONResponse:
    """Minimal route handler returning a fixed payload."""
    return JSONResponse({"id": "ev-001", "ssn": "123-45-6789", "cohort_size": 3, "name": "Test"})


def _build_app(pdp_result: dict[str, Any], fail_open: bool = True) -> Starlette:
    """Build a minimal Starlette app with PEP middleware wired to a mock PDP."""
    app = Starlette(routes=[Route("/api/v1/evidence/123", _evidence_endpoint)])
    app.add_middleware(PEPMiddleware, fail_open=fail_open)
    return app


@pytest.mark.asyncio
async def test_pep_permits_authorized_request() -> None:
    """PEP passes through when PDP returns PERMIT with no obligations."""
    app = _build_app(_make_permit_result())

    with patch(
        "src.api.middleware.pep.PEPMiddleware._call_pdp",
        new=AsyncMock(return_value=_make_permit_result()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/evidence/123")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "ev-001"
    assert resp.headers.get("x-pdp-decision") == "permit"


@pytest.mark.asyncio
async def test_pep_blocks_unauthorized_request() -> None:
    """PEP returns 403 when PDP returns DENY."""
    app = _build_app(_make_deny_result("insufficient_clearance"))

    with patch(
        "src.api.middleware.pep.PEPMiddleware._call_pdp",
        new=AsyncMock(return_value=_make_deny_result("insufficient_clearance")),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/evidence/123")

    assert resp.status_code == 403
    data = resp.json()
    assert data["reason"] == "insufficient_clearance"
    assert data["status_code"] == 403


@pytest.mark.asyncio
async def test_pep_applies_masking_obligation() -> None:
    """PEP masks SSN field in response when mask_fields obligation is present."""
    mask_obligation = {"type": "mask_fields", "params": {"fields": ["ssn"]}}
    pdp_result = _make_permit_result(obligations=[mask_obligation])
    app = _build_app(pdp_result)

    with patch(
        "src.api.middleware.pep.PEPMiddleware._call_pdp",
        new=AsyncMock(return_value=pdp_result),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/evidence/123")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ssn"] == "***"
    # Other fields should be intact
    assert data["id"] == "ev-001"


@pytest.mark.asyncio
async def test_pep_applies_suppression_obligation() -> None:
    """PEP returns 204 when suppress_cohort obligation fires."""
    # cohort_size=3 is below min_cohort=5 in the response payload
    suppress_obligation = {"type": "suppress_cohort", "params": {"min_cohort": 5}}
    pdp_result = _make_permit_result(obligations=[suppress_obligation])
    app = _build_app(pdp_result)

    with patch(
        "src.api.middleware.pep.PEPMiddleware._call_pdp",
        new=AsyncMock(return_value=pdp_result),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/evidence/123")

    # cohort_size=3 < 5 → suppressed → 204
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_pep_passthrough_unprotected_path() -> None:
    """PEP does not intercept unprotected paths."""

    async def open_endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    app = Starlette(routes=[Route("/api/v1/health", open_endpoint)])
    app.add_middleware(PEPMiddleware)

    # No PDP patch needed — it should not be called for /health
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_pep_fail_open_when_pdp_unavailable() -> None:
    """With fail_open=True, requests are permitted when PDP call raises."""
    app = _build_app(_make_permit_result(), fail_open=True)

    async def _raise(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("DB unavailable")

    with patch(
        "src.api.middleware.pep.PEPMiddleware._call_pdp",
        new=AsyncMock(side_effect=RuntimeError("DB unavailable")),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/evidence/123")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_pep_fail_closed_when_pdp_unavailable() -> None:
    """With fail_open=False, requests return 503 when PDP call raises."""
    app = _build_app(_make_permit_result(), fail_open=False)

    with patch(
        "src.api.middleware.pep.PEPMiddleware._call_pdp",
        new=AsyncMock(side_effect=RuntimeError("DB unavailable")),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/evidence/123")

    assert resp.status_code == 503
