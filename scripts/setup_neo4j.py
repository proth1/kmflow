"""Neo4j schema initialization script.

Creates constraints and indexes for the KMFlow knowledge graph.
Run this after Neo4j is up and accessible.

Usage:
    python -m scripts.setup_neo4j
"""

from __future__ import annotations

import asyncio
import sys

from neo4j import AsyncGraphDatabase


async def setup_schema(uri: str, user: str, password: str) -> None:
    """Create all Neo4j constraints and indexes."""
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    constraints = [
        ("Process", "id"),
        ("Subprocess", "id"),
        ("Activity", "id"),
        ("Decision", "id"),
        ("Evidence", "id"),
        ("Policy", "id"),
        ("Control", "id"),
        ("Regulation", "id"),
        ("TOM", "id"),
        ("Gap", "id"),
        ("Role", "id"),
        ("System", "id"),
        ("Document", "id"),
    ]

    indexes = [
        ("Process", "engagement_id"),
        ("Evidence", "engagement_id"),
        ("Evidence", "category"),
        ("Activity", "process_id"),
        ("Gap", "engagement_id"),
        ("Gap", "severity"),
    ]

    async with driver.session() as session:
        # Create uniqueness constraints
        for label, prop in constraints:
            query = f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
            await session.run(query)
            print(f"  Constraint: {label}.{prop} IS UNIQUE")

        # Create indexes
        for label, prop in indexes:
            query = f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.{prop})"
            await session.run(query)
            print(f"  Index: {label}.{prop}")

    await driver.close()
    print("\nNeo4j schema setup complete.")


def main() -> None:
    """Entry point for the setup script."""
    import os

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4j_dev_password")

    print(f"Connecting to Neo4j at {uri}...")
    asyncio.run(setup_schema(uri, user, password))


if __name__ == "__main__":
    main()
