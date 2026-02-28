"""Neo4j driver setup and session management.

Provides async Neo4j driver initialization, health checks,
and a dependency-injectable session for FastAPI route handlers.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession
from neo4j.exceptions import Neo4jError

from src.core.config import Settings

logger = logging.getLogger(__name__)


def create_neo4j_driver(settings: Settings) -> AsyncDriver:
    """Create an async Neo4j driver.

    Args:
        settings: Application settings with Neo4j connection details.

    Returns:
        An async Neo4j driver instance.
    """
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    return driver


async def verify_neo4j_connectivity(driver: AsyncDriver) -> bool:
    """Verify that the Neo4j driver can connect.

    Returns:
        True if the connection is successful, False otherwise.
    """
    try:
        await driver.verify_connectivity()
        return True
    except (Neo4jError, OSError):
        logger.exception("Failed to connect to Neo4j")
        return False


async def get_neo4j_session(driver: AsyncDriver) -> AsyncGenerator[AsyncSession, None]:
    """Yield a Neo4j session and ensure cleanup.

    This is used as a FastAPI dependency.
    """
    session = driver.session()
    try:
        yield session
    finally:
        await session.close()


async def setup_neo4j_constraints(driver: AsyncDriver) -> None:
    """Create initial Neo4j constraints and indexes.

    Sets up uniqueness constraints on node IDs and composite indexes
    for common query patterns.
    """
    constraints = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Process) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Activity) REQUIRE a.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Evidence) REQUIRE e.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (pol:Policy) REQUIRE pol.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Control) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Regulation) REQUIRE r.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (t:TOM) REQUIRE t.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (g:Gap) REQUIRE g.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (role:Role) REQUIRE role.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (s:System) REQUIRE s.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (sp:Subprocess) REQUIRE sp.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (dec:Decision) REQUIRE dec.id IS UNIQUE",
    ]

    indexes = [
        "CREATE INDEX IF NOT EXISTS FOR (p:Process) ON (p.engagement_id)",
        "CREATE INDEX IF NOT EXISTS FOR (e:Evidence) ON (e.engagement_id, e.category)",
        "CREATE INDEX IF NOT EXISTS FOR (a:Activity) ON (a.process_id)",
        "CREATE INDEX IF NOT EXISTS FOR (g:Gap) ON (g.engagement_id, g.severity)",
    ]

    async with driver.session() as session:
        for constraint in constraints:
            await session.run(constraint)
        for index in indexes:
            await session.run(index)

    logger.info("Neo4j constraints and indexes created")
