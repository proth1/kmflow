"""KMFlow FastAPI application entry point.

Configures the FastAPI app with:
- CORS middleware
- Lifespan events for database/cache connections
- Route registration (14 Phase 1-2 routers + 6 Phase 3 routers + 2 Phase 4 routers + 1 Phase 5 router)
- MCP server mounted at /mcp
- OpenAPI documentation at /docs
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware.audit import AuditLoggingMiddleware
from src.api.middleware.security import (
    RateLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from src.api.routes import (
    admin,
    auth,
    conformance,
    copilot,
    dashboard,
    engagements,
    evidence,
    graph,
    health,
    integrations,
    monitoring,
    patterns,
    portal,
    pov,
    regulatory,
    reports,
    shelf_requests,
    simulations,
    tom,
    users,
    websocket,
)
from src.core.config import get_settings
from src.core.database import create_engine
from src.core.neo4j import create_neo4j_driver, setup_neo4j_constraints, verify_neo4j_connectivity
from src.core.redis import create_redis_client, verify_redis_connectivity
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
        except Exception:
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
        version="0.6.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # -- Security Middleware ---
    # Note: middleware is applied in reverse order (last added = first executed)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AuditLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )

    # -- Phase 1-2 Routes ---
    app.include_router(health.router)
    app.include_router(engagements.router)
    app.include_router(evidence.router)
    app.include_router(shelf_requests.router)
    app.include_router(graph.router)
    app.include_router(pov.router)
    app.include_router(dashboard.router)
    app.include_router(auth.router)
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
    app.include_router(portal.router)
    app.include_router(mcp_router)

    # -- Phase 4 Routes ---
    app.include_router(copilot.router)
    app.include_router(conformance.router)

    # -- Phase 5 Routes ---
    app.include_router(admin.router)

    return app


# Application instance used by uvicorn
app = create_app()
