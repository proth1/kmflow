"""KMFlow FastAPI application entry point.

Configures the FastAPI app with:
- CORS middleware
- Lifespan events for database/cache connections
- Route registration
- OpenAPI documentation at /docs
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import dashboard, engagements, evidence, graph, health, pov, shelf_requests
from src.core.config import get_settings
from src.core.database import create_engine
from src.core.neo4j import create_neo4j_driver, setup_neo4j_constraints, verify_neo4j_connectivity
from src.core.redis import create_redis_client, verify_redis_connectivity

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown.

    On startup: initialize database connections, run Neo4j constraints.
    On shutdown: close all connections gracefully.
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

    yield

    # -- Shutdown ---
    await redis_client.aclose()
    await neo4j_driver.close()
    await engine.dispose()
    logger.info("All connections closed")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="AI-powered Process Intelligence platform for consulting engagements",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # -- CORS Middleware ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Routes ---
    app.include_router(health.router)
    app.include_router(engagements.router)
    app.include_router(evidence.router)
    app.include_router(shelf_requests.router)
    app.include_router(graph.router)
    app.include_router(pov.router)
    app.include_router(dashboard.router)

    return app


# Application instance used by uvicorn
app = create_app()
