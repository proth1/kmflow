"""Tests for the GDPR erasure background job (src/gdpr/erasure_job.py).

Covers _anonymize_user helper, run_erasure_job with various states,
and edge cases like missing users and no pending requests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.gdpr.erasure_job import _anonymize_user, run_erasure_job

# ---------------------------------------------------------------------------
# _anonymize_user
# ---------------------------------------------------------------------------


class TestAnonymizeUser:
    """Tests for the PII anonymisation helper."""

    @pytest.mark.asyncio
    async def test_anonymize_user_replaces_pii(self) -> None:
        """Should replace name, email, and clear sensitive fields."""
        user_id = uuid.uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.name = "John Doe"
        mock_user.email = "john@example.com"
        mock_user.is_active = True
        mock_user.hashed_password = "hashed"
        mock_user.external_id = "ext-123"

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        db.execute = AsyncMock(return_value=mock_result)

        await _anonymize_user(user_id, db)

        assert mock_user.name == "Deleted User"
        assert mock_user.email.startswith("deleted-")
        assert mock_user.email.endswith("@anonymized.local")
        assert mock_user.is_active is False
        assert mock_user.hashed_password is None
        assert mock_user.external_id is None
        # Should have been called twice: once for user select, once for audit UPDATE
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_anonymize_user_not_found(self) -> None:
        """Should log warning and skip when user not found."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        with patch("src.gdpr.erasure_job.logger") as mock_logger:
            await _anonymize_user(uuid.uuid4(), db)
            mock_logger.warning.assert_called_once()


# ---------------------------------------------------------------------------
# run_erasure_job
# ---------------------------------------------------------------------------


class TestRunErasureJob:
    """Tests for the periodic erasure job."""

    @pytest.mark.asyncio
    async def test_run_erasure_job_processes_due_requests(self) -> None:
        """Should anonymise users whose erasure_scheduled_at has passed."""
        user_id = uuid.uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.name = "Jane Doe"
        mock_user.email = "jane@example.com"
        mock_user.is_active = True
        mock_user.hashed_password = "hashed"
        mock_user.external_id = "ext-456"
        mock_user.erasure_requested_at = datetime.now(UTC) - timedelta(days=31)
        mock_user.erasure_scheduled_at = datetime.now(UTC) - timedelta(days=1)

        db = AsyncMock()

        # First execute: select users to erase
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [mock_user]

        # Second execute (inside _anonymize_user): select single user
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = mock_user

        # Third execute: UPDATE audit_logs
        update_result = MagicMock()

        db.execute = AsyncMock(side_effect=[select_result, user_result, update_result])
        db.commit = AsyncMock()

        count = await run_erasure_job(db)

        assert count == 1
        assert mock_user.erasure_requested_at is None
        assert mock_user.erasure_scheduled_at is None
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_erasure_job_no_pending_requests(self) -> None:
        """Should return 0 when no users are pending erasure."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        count = await run_erasure_job(db)

        assert count == 0
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_run_erasure_job_multiple_users(self) -> None:
        """Should process multiple users in a single run."""
        users = []
        for _ in range(3):
            user = MagicMock()
            user.id = uuid.uuid4()
            user.name = "User"
            user.email = "user@example.com"
            user.is_active = True
            user.hashed_password = "hashed"
            user.external_id = None
            user.erasure_requested_at = datetime.now(UTC) - timedelta(days=31)
            user.erasure_scheduled_at = datetime.now(UTC) - timedelta(days=1)
            users.append(user)

        db = AsyncMock()

        # First call: select users to erase
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = users

        # For each user: select user + UPDATE audit_logs
        side_effects = [select_result]
        for u in users:
            user_result = MagicMock()
            user_result.scalar_one_or_none.return_value = u
            side_effects.append(user_result)
            side_effects.append(MagicMock())  # UPDATE result

        db.execute = AsyncMock(side_effect=side_effects)
        db.commit = AsyncMock()

        count = await run_erasure_job(db)

        assert count == 3
        for u in users:
            assert u.erasure_requested_at is None
            assert u.erasure_scheduled_at is None
