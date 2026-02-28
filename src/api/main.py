"""KMFlow FastAPI application entry point.

Configures the FastAPI app with:
- CORS middleware
- Lifespan events for database/cache connections
- Route registration (14 Phase 1-2 routers + 6 Phase 3 routers + 2 Phase 4 routers
  + 1 Phase 5 router + Phase C lineage router + Phase D governance router)
- MCP server mounted at /mcp
- OpenAPI documentation at /docs (debug mode only)
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j.exceptions import Neo4jError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.api.middleware.audit import AuditLoggingMiddleware
from src.api.middleware.security import (
    RateLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from src.api.routes import (
    admin,
    assumptions,
    audit_logs,
    camunda,
    claim_write_back,
    cohort,
    conflicts,
    conformance,
    consent,
    consistency,
    cost_modeling,
    copilot,
    dashboard,
    data_classification,
    deviations,
    engagements,
    event_spine,
    evidence,
    evidence_coverage,
    evidence_gap_ranking,
    exports,
    gap_probes,
    gdpr,
    governance,
    governance_flags,
    governance_overlay,
    graph,
    health,
    incidents,
    integrations,
    knowledge_forms,
    lineage,
    llm_audit,
    metrics,
    micro_surveys,
    monitoring,
    patterns,
    pdp,
    portal,
    pov,
    raci,
    regulatory,
    reports,
    scenario_comparison,
    scenarios,
    seed_lists,
    sensitivity,
    shelf_requests,
    simulations,
    survey_claims,
    survey_sessions,
    taskmining,
    tom,
    transfer_controls,
    users,
    validation,
    websocket,
)
from src.api.routes import (
    annotations as annotations_routes,
)
from src.api.routes import (
    auth as auth_routes,
)
from src.api.routes.auth import limiter
from src.api.version import API_VERSION
from src.core.config import get_settings
from src.core.database import create_engine
from src.core.neo4j import create_neo4j_driver, setup_neo4j_constraints, verify_neo4j_connectivity
from src.core.redis import create_redis_client, verify_redis_connectivity
from src.integrations.camunda import CamundaClient
from src.mcp.server import router as mcp_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown.

    On startup: initialize database connections, run Neo4j constraints,
    start monitoring workers.
    On shutdown: close all connections and stop workers gracefully.
    """
    settings = get_settings()

    # -- PostgreSQL ---
    engine, session_factory = create_engine(settings)
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory
    logger.info("PostgreSQL connection pool initialized")

    # -- Neo4j ---
    neo4j_driver = create_neo4j_driver(settings)
    app.state.neo4j_driver = neo4j_driver
    if await verify_neo4j_connectivity(neo4j_driver):
        logger.info("Neo4j connection verified")
        try:
            await setup_neo4j_constraints(neo4j_driver)
        except Neo4jError:
            logger.warning("Failed to setup Neo4j constraints (non-fatal)")
    else:
        logger.warning("Neo4j is not reachable; starting in degraded mode")

    # -- Redis ---
    redis_client = create_redis_client(settings)
    app.state.redis_client = redis_client
    if await verify_redis_connectivity(redis_client):
        logger.info("Redis connection verified")
    else:
        logger.warning("Redis is not reachable; starting in degraded mode")

    # -- CIB7 (Camunda) ---
    cib7_url = os.environ.get("CIB7_URL", "http://localhost:8080/engine-rest")
    camunda_client = CamundaClient(cib7_url)
    app.state.camunda_client = camunda_client
    if await camunda_client.verify_connectivity():
        logger.info("CIB7 Camunda engine connection verified")
    else:
        logger.warning("CIB7 is not reachable; starting in degraded mode")

    # -- Monitoring Workers ---
    shutdown_event = asyncio.Event()
    app.state.monitoring_shutdown = shutdown_event
    worker_tasks = []

    if settings.monitoring_worker_count > 0:
        from src.monitoring.worker import run_worker

        for i in range(settings.monitoring_worker_count):
            task = asyncio.create_task(run_worker(redis_client, f"worker-{i}", shutdown_event))
            worker_tasks.append(task)
        logger.info("Started %d monitoring workers", settings.monitoring_worker_count)

    # -- Task Mining Workers ---
    if settings.taskmining_enabled and settings.taskmining_worker_count > 0:
        from src.taskmining.worker import run_worker as run_tm_worker

        for i in range(settings.taskmining_worker_count):
            task = asyncio.create_task(run_tm_worker(redis_client, f"tm-worker-{i}", shutdown_event))
            worker_tasks.append(task)
        logger.info("Started %d task mining workers", settings.taskmining_worker_count)

    app.state.worker_tasks = worker_tasks

    yield

    # -- Shutdown ---
    shutdown_event.set()
    for task in worker_tasks:
        task.cancel()
    if worker_tasks:
        await asyncio.gather(*worker_tasks, return_exceptions=True)
        logger.info("Monitoring workers stopped")

    await redis_client.close()
    await neo4j_driver.close()
    await engine.dispose()
    logger.info("All connections closed")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="AI-powered Process Intelligence platform for consulting engagements",
        version=API_VERSION,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # -- Rate Limiter (slowapi) ---
    # Register the limiter on app.state so SlowAPIMiddleware and the
    # @limiter.limit decorators on individual routes can find it.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # -- Security Middleware ---
    # Note: middleware is applied in reverse order (last added = first executed).
    # SlowAPIMiddleware is added last so it runs first in the request pipeline.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Accept"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AuditLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
    app.add_middleware(SlowAPIMiddleware)

    # -- Phase 1-2 Routes ---
    app.include_router(health.router)
    app.include_router(engagements.router)
    app.include_router(evidence.router)
    app.include_router(shelf_requests.router)
    app.include_router(graph.router)
    app.include_router(pov.router)
    app.include_router(dashboard.router)
    app.include_router(auth_routes.router)
    app.include_router(users.router)
    app.include_router(regulatory.router)
    app.include_router(tom.router)
    app.include_router(integrations.router)
    app.include_router(reports.router)

    # -- Phase 3 Routes ---
    app.include_router(monitoring.router)
    app.include_router(websocket.router)
    app.include_router(patterns.router)
    app.include_router(simulations.router)
    app.include_router(scenario_comparison.router)  # Must precede scenarios (static /compare before /{id})
    app.include_router(scenarios.router)
    app.include_router(portal.router)
    app.include_router(mcp_router)
    app.include_router(camunda.router)

    # -- Phase 4 Routes ---
    app.include_router(copilot.router)
    app.include_router(conformance.router)

    # -- Phase 8 Routes ---
    app.include_router(metrics.router)
    app.include_router(annotations_routes.router)
    app.include_router(raci.router)

    # -- Phase C: Data Layer Evolution ---
    app.include_router(lineage.router)

    # -- Phase D: Data Governance Framework ---
    app.include_router(governance.router)
    app.include_router(governance_overlay.router)

    # -- Phase 5 Routes ---
    app.include_router(admin.router)

    # -- GDPR Routes (Issue #165) ---
    app.include_router(gdpr.router)

    # -- Task Mining Routes ---
    app.include_router(taskmining.router)

    # -- Audit Log Query Routes (Story #314) ---
    app.include_router(audit_logs.router)

    # -- Deviation Detection Routes (Story #350) ---
    app.include_router(deviations.router)

    # -- Review Pack Validation Routes (Story #349) ---
    app.include_router(validation.router)

    # -- Conflict Resolution Routes (Story #388) ---
    app.include_router(conflicts.router)

    # -- Consistency Reporting Routes (Story #392) ---
    app.include_router(consistency.router)

    # -- Knowledge Forms Coverage Routes (Story #316) ---
    app.include_router(knowledge_forms.router)

    # -- Event Spine Routes (Story #334) ---
    app.include_router(event_spine.router)

    # -- Gap Probe Routes (Story #327) ---
    app.include_router(gap_probes.router)

    # -- Evidence Gap Ranking Routes (Story #393) ---
    app.include_router(evidence_gap_ranking.router)

    # -- Micro-Survey Routes (Story #398) ---
    app.include_router(micro_surveys.router)

    # -- Seed List Routes (Story #321) ---
    app.include_router(seed_lists.router)

    # -- Survey Claim Routes (Story #322) ---
    app.include_router(survey_claims.router)

    # -- Survey Session Routes (Story #319) ---
    app.include_router(survey_sessions.router)

    # -- Incident Response Routes (Story #397) ---
    app.include_router(incidents.router)

    # -- Transfer Control Routes (Story #395) ---
    app.include_router(transfer_controls.router)

    # -- PDP Routes (Story #377) ---
    app.include_router(pdp.router)

    # -- Cohort Suppression Routes (Story #391) ---
    app.include_router(cohort.router)

    # -- LLM Audit Trail Routes (Story #386) ---
    app.include_router(llm_audit.router)

    # -- Evidence Coverage Routes (Story #385) ---
    app.include_router(evidence_coverage.router)

    # -- Export Watermarking Routes (Story #387) ---
    app.include_router(exports.router)

    # -- Consent Architecture Routes (Story #382) ---
    app.include_router(consent.router)

    # -- Data Classification & GDPR Compliance Routes (Story #317) ---
    app.include_router(data_classification.router)

    # -- Claim Write-Back Routes (Story #324) ---
    app.include_router(claim_write_back.router)

    # -- Financial Assumption Routes (Story #354) ---
    app.include_router(assumptions.router)

    # -- Cost Modeling Routes (Story #359) ---
    app.include_router(cost_modeling.router)

    # -- Governance Flag Detection Routes (Story #381) ---
    app.include_router(governance_flags.router)

    # -- Sensitivity Analysis Routes (Story #364) ---
    app.include_router(sensitivity.router)

    # -- Error Handlers ---
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.warning("Validation error [%s]: %s", request_id, exc)
        return JSONResponse(
            status_code=422,
            content={"detail": str(exc), "request_id": request_id},
        )

    @app.exception_handler(Exception)  # Intentionally broad: top-level global error handler
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception("Unhandled error [%s]: %s", request_id, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )

    return app


# Application instance used by uvicorn
app = create_app()
