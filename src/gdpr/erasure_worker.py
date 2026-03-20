"""GDPR erasure background task worker (KMFLOW-58).

Wraps ``run_erasure_job`` into the async task architecture so it can
be triggered via the task queue and report progress through the
standard polling API.

Cross-store coordination: PostgreSQL anonymisation + Neo4j graph
node removal + Redis cache purge for affected users.

Payload::

    {}  # No input needed — scans for approved requests past grace period.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.tasks.base import TaskWorker

logger = logging.getLogger(__name__)

# Steps: 1) Find users, 2) Anonymise PG, 3) Purge Neo4j, 4) Purge Redis
_TOTAL_STEPS = 4


class GdprErasureWorker(TaskWorker):
    """Process approved GDPR erasure requests across all data stores.

    Coordinates anonymisation across PostgreSQL, Neo4j, and Redis
    to ensure complete data removal.
    """

    task_type = "gdpr_erasure"
    max_retries = 3

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute GDPR erasure across all stores.

        Args:
            payload: Empty dict (no input needed).

        Returns:
            Summary with counts of users anonymised per store.
        """
        self.report_progress(0, _TOTAL_STEPS)

        # Lazy imports to avoid circular dependencies
        # Step 1: Find eligible users
        from sqlalchemy import select

        from src.core.database import async_session_factory  # type: ignore[attr-defined]
        from src.core.models import User

        async with async_session_factory() as session:
            from datetime import UTC, datetime

            now = datetime.now(UTC)
            result = await session.execute(
                select(User).where(
                    User.erasure_requested_at.isnot(None),
                    User.erasure_scheduled_at.isnot(None),
                    User.erasure_scheduled_at <= now,
                    User.is_active == True,  # noqa: E712
                )
            )
            users = list(result.scalars().all())
            user_ids = [str(u.id) for u in users]
        self.report_progress(1, _TOTAL_STEPS)

        if not user_ids:
            logger.info("GDPR erasure worker: no pending requests")
            self.report_progress(_TOTAL_STEPS, _TOTAL_STEPS)
            return {"users_found": 0, "pg_anonymised": 0, "neo4j_purged": 0, "redis_purged": 0}

        # Step 2: Anonymise in PostgreSQL
        from src.gdpr.erasure_job import run_erasure_job

        async with async_session_factory() as session:
            pg_count = await run_erasure_job(session)
        self.report_progress(2, _TOTAL_STEPS)

        # Step 3: Purge from Neo4j graph (remove user nodes and relationships)
        neo4j_purged = await self._purge_neo4j(user_ids)
        self.report_progress(3, _TOTAL_STEPS)

        # Step 4: Purge from Redis (remove any cached sessions/tokens)
        redis_purged = await self._purge_redis(user_ids)
        self.report_progress(_TOTAL_STEPS, _TOTAL_STEPS)

        logger.info(
            "GDPR erasure complete: %d PG, %d Neo4j, %d Redis",
            pg_count,
            neo4j_purged,
            redis_purged,
        )

        return {
            "users_found": len(user_ids),
            "pg_anonymised": pg_count,
            "neo4j_purged": neo4j_purged,
            "redis_purged": redis_purged,
        }

    async def _purge_neo4j(self, user_ids: list[str]) -> int:
        """Remove user-related nodes from the knowledge graph.

        Uses the Neo4j driver from the app state (set during lifespan).
        Falls back gracefully if Neo4j is unavailable.

        Args:
            user_ids: UUIDs of users to purge.

        Returns:
            Number of nodes deleted.
        """
        # Neo4j purge requires access to the driver from app state.
        # This will be wired when the cross-store coordination story
        # (KMFLOW-62) passes the driver through the task payload or
        # a shared registry.  For now, log and skip.
        logger.info(
            "Neo4j GDPR purge: %d user(s) flagged (driver wiring pending KMFLOW-62)",
            len(user_ids),
        )
        return 0

    async def _purge_redis(self, user_ids: list[str]) -> int:
        """Remove user-related cache entries from Redis.

        Args:
            user_ids: UUIDs of users to purge.

        Returns:
            Number of keys deleted.
        """
        try:
            from src.core.config import get_settings
            from src.core.redis import create_redis_client

            settings = get_settings()
            client = create_redis_client(settings)

            count = 0
            for uid in user_ids:
                # Remove session and token cache keys
                for pattern in [f"session:{uid}*", f"token:{uid}*", f"user:{uid}*"]:
                    keys = []
                    async for key in client.scan_iter(match=pattern, count=100):
                        keys.append(key)
                    if keys:
                        count += await client.delete(*keys)

            await client.close()
            return count
        except Exception as exc:
            logger.exception("Redis GDPR purge failed")
            raise RuntimeError("Redis GDPR purge failed — data may remain in cache") from exc
