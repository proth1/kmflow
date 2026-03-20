"""Tests for GDPR erasure worker (src/gdpr/erasure_worker.py).

Covers GdprErasureWorker execution across all 4 stores:
no pending users, one user processed, Neo4j failure, Redis failure.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.gdpr.erasure_worker import GdprErasureWorker


@pytest.fixture
def worker():
    """Create a GdprErasureWorker instance."""
    return GdprErasureWorker()


def _make_user(*, active: bool = True) -> MagicMock:
    """Create a mock user with erasure fields set."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.name = "Test User"
    user.email = "test@example.com"
    user.is_active = active
    user.hashed_password = "hashed"
    user.external_id = None
    user.erasure_requested_at = datetime.now(UTC) - timedelta(days=31)
    user.erasure_scheduled_at = datetime.now(UTC) - timedelta(days=1)
    return user


def _mock_session_factory(*sessions):
    """Create a mock async context manager factory that yields sessions in order."""
    call_idx = 0

    def factory():
        nonlocal call_idx
        session = sessions[call_idx % len(sessions)]
        call_idx += 1
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    return MagicMock(side_effect=factory)


class TestGdprErasureWorker:
    """Tests for the erasure worker execute method."""

    @pytest.mark.asyncio
    async def test_no_pending_users(self, worker) -> None:
        """Should return zeros when no users are pending erasure."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = _mock_session_factory(mock_session)

        import src.core.database as db_mod

        with patch.object(db_mod, "async_session_factory", mock_factory, create=True):
            result = await worker.execute({})

        assert result["users_found"] == 0
        assert result["pg_anonymised"] == 0
        assert result["neo4j_purged"] == 0
        assert result["redis_purged"] == 0

    @pytest.mark.asyncio
    async def test_one_user_processed(self, worker) -> None:
        """Should process one user across all stores."""
        user = _make_user()

        # Session for finding users
        find_session = AsyncMock()
        find_result = MagicMock()
        find_result.scalars.return_value.all.return_value = [user]
        find_session.execute = AsyncMock(return_value=find_result)

        # Session for erasure job
        erase_session = AsyncMock()
        erase_select_result = MagicMock()
        erase_select_result.scalars.return_value.all.return_value = [user]
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        erase_session.execute = AsyncMock(side_effect=[erase_select_result, user_result, MagicMock()])
        erase_session.commit = AsyncMock()

        mock_factory = _mock_session_factory(find_session, erase_session)

        import src.core.database as db_mod

        with (
            patch.object(db_mod, "async_session_factory", mock_factory, create=True),
            patch.object(worker, "_purge_neo4j", new_callable=AsyncMock, return_value=1),
            patch.object(worker, "_purge_redis", new_callable=AsyncMock, return_value=2),
        ):
            result = await worker.execute({})

        assert result["users_found"] == 1
        assert result["neo4j_purged"] == 1
        assert result["redis_purged"] == 2

    @pytest.mark.asyncio
    async def test_neo4j_failure(self, worker) -> None:
        """Neo4j purge returns 0 when driver is not wired (per KMFLOW-62)."""
        user = _make_user()

        # Session for finding users
        find_session = AsyncMock()
        find_result = MagicMock()
        find_result.scalars.return_value.all.return_value = [user]
        find_session.execute = AsyncMock(return_value=find_result)

        # Session for erasure job
        erase_session = AsyncMock()
        erase_select_result = MagicMock()
        erase_select_result.scalars.return_value.all.return_value = [user]
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        erase_session.execute = AsyncMock(side_effect=[erase_select_result, user_result, MagicMock()])
        erase_session.commit = AsyncMock()

        mock_factory = _mock_session_factory(find_session, erase_session)

        import src.core.database as db_mod

        with (
            patch.object(db_mod, "async_session_factory", mock_factory, create=True),
            patch.object(worker, "_purge_redis", new_callable=AsyncMock, return_value=1),
        ):
            result = await worker.execute({})

        # Neo4j purge returns 0 (driver not wired yet per KMFLOW-62)
        assert result["neo4j_purged"] == 0

    @pytest.mark.asyncio
    async def test_redis_failure(self, worker) -> None:
        """Should raise RuntimeError on Redis failure (data may remain in cache)."""
        user = _make_user()

        # Session for finding users
        find_session = AsyncMock()
        find_result = MagicMock()
        find_result.scalars.return_value.all.return_value = [user]
        find_session.execute = AsyncMock(return_value=find_result)

        # Session for erasure job
        erase_session = AsyncMock()
        erase_select_result = MagicMock()
        erase_select_result.scalars.return_value.all.return_value = [user]
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        erase_session.execute = AsyncMock(side_effect=[erase_select_result, user_result, MagicMock()])
        erase_session.commit = AsyncMock()

        mock_factory = _mock_session_factory(find_session, erase_session)

        import src.core.database as db_mod

        with (
            patch.object(db_mod, "async_session_factory", mock_factory, create=True),
            patch.object(worker, "_purge_neo4j", new_callable=AsyncMock, return_value=0),
            patch("src.core.redis.create_redis_client", side_effect=ConnectionError("Redis down")),
            pytest.raises(RuntimeError, match="Redis GDPR purge failed"),
        ):
            await worker.execute({})
