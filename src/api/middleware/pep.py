"""Policy Enforcement Point (PEP) middleware for FastAPI.

Intercepts requests to protected endpoints, calls the PDP evaluate() with
request context, enforces returned obligations (field masking, cohort
suppression), and blocks the request with 403 if the decision is DENY.

The PEP operates on the response body for PERMIT decisions that carry
masking or suppression obligations. It re-serializes the JSON response
after applying obligations so callers always receive sanitized data.

Endpoints are opted-in to PEP enforcement via the PROTECTED_PATH_PREFIXES
set. Paths not in this set pass through unchanged so health checks and
auth endpoints are never blocked.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from src.core.models.pdp import ObligationType, PDPDecisionType

logger = logging.getLogger(__name__)

# Path prefixes that require PEP enforcement. Requests to these prefixes
# are evaluated by the PDP. All other paths pass through unchanged.
PROTECTED_PATH_PREFIXES: frozenset[str] = frozenset(
    {
        "/api/v1/evidence",
        "/api/v1/knowledge-graph",
        "/api/v1/engagements",
        "/api/v1/tom",
        "/api/v1/gap",
        "/api/v1/semantic",
    }
)

# Paths always excluded from PEP regardless of prefix matching
_SKIP_PATHS: frozenset[str] = frozenset({"/api/v1/health", "/docs", "/openapi.json", "/redoc", "/api/v1/pdp"})

# Maximum response body size to apply obligations to (10 MB). Larger
# responses are passed through to avoid excessive memory allocation.
_MAX_BODY_BYTES = 10 * 1024 * 1024


def _is_protected(path: str) -> bool:
    """Return True if this path requires PEP enforcement."""
    if path in _SKIP_PATHS:
        return False
    return any(path.startswith(prefix) for prefix in PROTECTED_PATH_PREFIXES)


def _extract_engagement_id(path: str) -> str | None:
    """Parse engagement_id UUID from URL path if present."""
    parts = path.split("/")
    try:
        idx = parts.index("engagements")
        candidate = parts[idx + 1] if idx + 1 < len(parts) else None
        if candidate:
            uuid.UUID(candidate)  # validate
            return candidate
    except (ValueError, IndexError):
        pass
    return None


def _extract_actor(request: Request) -> tuple[str, str]:
    """Return (actor, actor_role) from request state or fallback."""
    user = getattr(request.state, "user", None)
    if user is not None:
        actor = str(getattr(user, "email", "") or getattr(user, "id", "anonymous"))
        actor_role = str(getattr(user, "role", "client_viewer"))
        # Unwrap StrEnum value if needed
        if hasattr(actor_role, "value"):
            actor_role = actor_role.value  # type: ignore[union-attr]
        return actor, actor_role
    return "anonymous", "client_viewer"


def _extract_attributes(request: Request) -> dict[str, Any]:
    """Build ABAC attribute dict from request state and headers.

    Attributes are set by auth middleware or upstream enrichment layers.
    Falls back to empty dict so evaluation still succeeds without ABAC attrs.
    """
    attrs: dict[str, Any] = {}
    abac = getattr(request.state, "abac_attributes", None)
    if isinstance(abac, dict):
        attrs.update(abac)
    # Note: cohort_size must be derived server-side from response data by
    # the upstream enrichment middleware that populates request.state.abac_attributes.
    # It is NOT read from client headers to prevent self-reported bypass of
    # cohort suppression obligations.
    return attrs


async def _read_body(request: Request) -> bytes:
    """Read and buffer the request body so it can be re-used by downstream."""
    body = await request.body()
    return body


class PEPMiddleware(BaseHTTPMiddleware):
    """Enforce PDP decisions for protected API endpoints.

    Flow:
    1. Check if path is protected. If not, pass through.
    2. Call PDP.evaluate() with request context.
    3. If DENY → return 403 immediately (request never reaches route handler).
    4. If PERMIT → let request proceed, then apply obligations to response body.

    The PEP is intentionally fail-open for non-JSON or oversized responses:
    obligation enforcement is skipped but the PERMIT decision stands. This
    ensures the PEP never breaks non-JSON endpoints (binary downloads, SSE).
    """

    def __init__(self, app: ASGIApp, *, fail_open: bool | None = None) -> None:
        super().__init__(app)
        # fail_open controls behavior when PDP is unavailable:
        #   True  → requests are permitted (development/testing)
        #   False → requests get 503 (production)
        # Default: read from settings; if not configured, default False.
        if fail_open is not None:
            self._fail_open = fail_open
        else:
            from src.core.config import get_settings

            settings = get_settings()
            self._fail_open = getattr(settings, "pdp_fail_open", False)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not _is_protected(request.url.path):
            return await call_next(request)

        actor, actor_role = _extract_actor(request)
        attributes = _extract_attributes(request)
        engagement_id_str = _extract_engagement_id(request.url.path)
        request_id = getattr(request.state, "request_id", None)

        # Derive resource_id from path (best-effort)
        resource_id = request.url.path

        # Determine classification from request state (set by auth/enrichment)
        classification = str(getattr(request.state, "data_classification", "internal"))
        operation = _method_to_operation(request.method)

        try:
            pdp_result = await self._call_pdp(
                request=request,
                engagement_id_str=engagement_id_str,
                actor=actor,
                actor_role=actor_role,
                resource_id=resource_id,
                classification=classification,
                operation=operation,
                attributes=attributes,
                request_id=request_id,
            )
        except Exception as exc:
            logger.warning("PEP: PDP call failed (fail_open=%s): %s", self._fail_open, exc)
            if not self._fail_open:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Policy service unavailable", "status_code": 503},
                )
            # Fail open: proceed without enforcement
            return await call_next(request)

        decision = pdp_result.get("decision")
        if decision == PDPDecisionType.DENY:
            logger.info(
                "PEP: DENY actor=%s role=%s path=%s reason=%s",
                actor,
                actor_role,
                request.url.path,
                pdp_result.get("reason"),
            )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Access denied by policy",
                    "reason": pdp_result.get("reason"),
                    "status_code": 403,
                },
                headers={"X-PDP-Audit-ID": pdp_result.get("audit_id", "")},
            )

        # PERMIT — execute route handler then apply obligations to response
        response = await call_next(request)
        obligations = pdp_result.get("obligations", [])

        if obligations and response.status_code < 300:
            response = await self._apply_response_obligations(response, obligations, actor)

        response.headers["X-PDP-Decision"] = "permit"
        response.headers["X-PDP-Audit-ID"] = pdp_result.get("audit_id", "")
        return response

    async def _call_pdp(
        self,
        *,
        request: Request,
        engagement_id_str: str | None,
        actor: str,
        actor_role: str,
        resource_id: str,
        classification: str,
        operation: str,
        attributes: dict[str, Any],
        request_id: str | None,
    ) -> dict[str, Any]:
        """Invoke PDPService.evaluate() using the app's session factory."""
        from src.api.services.pdp import PDPService

        session_factory = getattr(request.app.state, "db_session_factory", None)
        if session_factory is None:
            # No DB available — default PERMIT (allows tests without a DB)
            logger.debug("PEP: no session factory, defaulting PERMIT")
            return {
                "decision": PDPDecisionType.PERMIT,
                "obligations": [],
                "reason": "no_db",
                "audit_id": str(uuid.uuid4()),
            }

        # Use a fallback engagement_id when path doesn't contain one
        eng_id = uuid.UUID(engagement_id_str) if engagement_id_str else uuid.UUID(int=0)

        async with session_factory() as session:
            service = PDPService(session)
            result = await service.evaluate(
                engagement_id=eng_id,
                actor=actor,
                actor_role=actor_role,
                resource_id=resource_id,
                classification=classification,
                operation=operation,
                attributes=attributes,
                request_id=request_id,
            )
            await session.commit()
        return result

    async def _apply_response_obligations(
        self,
        response: Response,
        obligations: list[dict[str, Any]],
        actor: str,
    ) -> Response:
        """Apply masking/suppression obligations to the JSON response body.

        Returns the original response unchanged when:
        - Content-Type is not application/json
        - Body exceeds _MAX_BODY_BYTES
        - Body cannot be parsed as JSON
        """
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        body_bytes = b""
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            body_bytes += chunk if isinstance(chunk, bytes) else chunk.encode()
            if len(body_bytes) > _MAX_BODY_BYTES:
                logger.warning("PEP: response body too large for obligation enforcement, skipping")
                return response

        try:
            data = json.loads(body_bytes)
        except (json.JSONDecodeError, ValueError):
            return response

        from src.api.services.obligation_enforcer import ObligationEnforcer

        # Convert raw obligation dicts into PolicyObligation-like objects for enforcer
        obligation_objects = [_dict_to_obligation(o) for o in obligations]
        data = ObligationEnforcer.enforce_all(data, obligation_objects, actor=actor)

        if data is None:
            # Cohort suppression returned None — return empty 204
            return Response(status_code=204, headers=dict(response.headers))

        new_body = json.dumps(data).encode()
        response.headers["content-length"] = str(len(new_body))
        return Response(
            content=new_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type="application/json",
        )


def _method_to_operation(method: str) -> str:
    """Map HTTP method to PDP operation type."""
    return {
        "GET": "read",
        "HEAD": "read",
        "POST": "write",
        "PUT": "write",
        "PATCH": "write",
        "DELETE": "delete",
    }.get(method.upper(), "read")


def _dict_to_obligation(raw: dict[str, Any]) -> Any:
    """Convert an obligation dict to a simple namespace for the enforcer.

    Uses a lightweight object so ObligationEnforcer doesn't need a DB model.
    """
    from types import SimpleNamespace

    raw_type = raw.get("type", "")
    try:
        ob_type = ObligationType(raw_type)
    except ValueError:
        ob_type = raw_type  # type: ignore[assignment]

    return SimpleNamespace(
        obligation_type=ob_type,
        parameters=raw.get("params") or raw.get("parameters") or {},
    )
