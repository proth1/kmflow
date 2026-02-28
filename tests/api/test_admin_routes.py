"""Tests for admin-only routes (src/api/routes/admin.py).

Covers:
- POST /api/v1/admin/retention-cleanup
  - Non-admin (PROCESS_ANALYST) receives 403
  - Dry run returns preview without deleting
  - Live run without X-Confirm-Action header is rejected with 400
  - Live run with correct confirmation header executes cleanup
- POST /api/v1/admin/rotate-encryption-key
  - Non-admin (PROCESS_ANALYST) receives 403
  - Admin with no credentials to rotate returns 0 rotated
  - Admin with credentials triggers re-encryption
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.auth import create_access_token, get_current_user, hash_password
from src.core.config import Settings
from src.core.models import Engagement, EngagementStatus, User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _test_settings() -> Settings:
    return Settings(
        jwt_secret_key="test-secret-key-for-tests",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        auth_dev_mode=True,
        monitoring_worker_count=0,
    )


def _make_user(role: UserRole, **kwargs) -> User:  # noqa: ANN003
    """Create a minimal User ORM object."""
    defaults = {
        "id": uuid.uuid4(),
        "email": f"{role.value}@example.com",
        "name": role.value.replace("_", " ").title(),
        "role": role,
        "is_active": True,
        "hashed_password": hash_password("password"),
    }
    defaults.update(kwargs)
    return User(**defaults)


def _make_engagement(
    days_old: int = 400,
    retention_days: int = 365,
    status: EngagementStatus = EngagementStatus.COMPLETED,
) -> Engagement:
    """Build a minimal Engagement with a created_at set to days_old ago."""
    from datetime import UTC, datetime, timedelta

    eng = MagicMock(spec=Engagement)
    eng.id = uuid.uuid4()
    eng.name = "Old Engagement"
    eng.retention_days = retention_days
    eng.status = status
    eng.created_at = datetime.now(UTC) - timedelta(days=days_old)
    return eng


def _admin_token(user: User) -> str:
    settings = _test_settings()
    return create_access_token({"sub": str(user.id)}, settings)


def _mock_scalar_result(value) -> MagicMock:  # noqa: ANN001
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalars_result(items: list) -> MagicMock:
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result = MagicMock()
    result.scalars.return_value = scalars_mock
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _use_real_auth(test_app):
    """Remove the global get_current_user override so role checks are exercised."""
    test_app.dependency_overrides.pop(get_current_user, None)
    yield
    # Restore so that other tests in the session continue to use the stub
    mock_user = MagicMock(spec=User)
    mock_user.id = uuid.uuid4()
    mock_user.email = "testuser@kmflow.dev"
    mock_user.role = UserRole.PLATFORM_ADMIN
    mock_user.is_active = True
    test_app.dependency_overrides[get_current_user] = lambda: mock_user


# ---------------------------------------------------------------------------
# POST /api/v1/admin/retention-cleanup
# ---------------------------------------------------------------------------


class TestRetentionCleanup:
    """Tests for POST /api/v1/admin/retention-cleanup."""

    @pytest.mark.asyncio
    async def test_retention_cleanup_requires_admin(self, test_app, mock_db_session: AsyncMock) -> None:
        """A PROCESS_ANALYST user receives 403 Forbidden."""
        analyst = _make_user(UserRole.PROCESS_ANALYST)
        # Return the analyst for the DB lookup triggered by get_current_user
        mock_db_session.execute.return_value = _mock_scalar_result(analyst)

        token = _admin_token(analyst)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/admin/retention-cleanup",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_retention_cleanup_dry_run(self, test_app, mock_db_session: AsyncMock) -> None:
        """Dry run (default) returns a preview without performing any deletion."""
        admin = _make_user(UserRole.PLATFORM_ADMIN)
        expired_eng = _make_engagement()

        mock_db_session.execute.return_value = _mock_scalar_result(admin)

        token = _admin_token(admin)

        with patch(
            "src.core.retention.find_expired_engagements",
            new=AsyncMock(return_value=[expired_eng]),
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/admin/retention-cleanup?dry_run=true",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True
        assert data["would_clean_up"] == 1
        assert data["status"] == "preview"
        assert len(data["engagements"]) == 1

    @pytest.mark.asyncio
    async def test_retention_cleanup_requires_confirmation_header(self, test_app, mock_db_session: AsyncMock) -> None:
        """A live run without the X-Confirm-Action header returns 400."""
        admin = _make_user(UserRole.PLATFORM_ADMIN)
        mock_db_session.execute.return_value = _mock_scalar_result(admin)

        token = _admin_token(admin)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/admin/retention-cleanup?dry_run=false",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 400
        assert "X-Confirm-Action" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_retention_cleanup_wrong_confirmation_value_returns_400(
        self, test_app, mock_db_session: AsyncMock
    ) -> None:
        """Providing X-Confirm-Action with an incorrect value returns 400."""
        admin = _make_user(UserRole.PLATFORM_ADMIN)
        mock_db_session.execute.return_value = _mock_scalar_result(admin)

        token = _admin_token(admin)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/admin/retention-cleanup?dry_run=false",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Confirm-Action": "wrong-value",
                },
            )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_retention_cleanup_live_run_executes(self, test_app, mock_db_session: AsyncMock) -> None:
        """A live run with the correct confirmation header returns cleaned_up count."""
        admin = _make_user(UserRole.PLATFORM_ADMIN)
        mock_db_session.execute.return_value = _mock_scalar_result(admin)

        token = _admin_token(admin)

        with patch(
            "src.core.retention.cleanup_expired_engagements",
            new=AsyncMock(return_value=3),
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/admin/retention-cleanup?dry_run=false",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Confirm-Action": "retention-cleanup",
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is False
        assert data["cleaned_up"] == 3
        assert data["status"] == "completed"


# ---------------------------------------------------------------------------
# POST /api/v1/admin/rotate-encryption-key
# ---------------------------------------------------------------------------


class TestRotateEncryptionKey:
    """Tests for POST /api/v1/admin/rotate-encryption-key."""

    @pytest.mark.asyncio
    async def test_key_rotation_requires_admin(self, test_app, mock_db_session: AsyncMock) -> None:
        """A PROCESS_ANALYST user receives 403 Forbidden."""
        analyst = _make_user(UserRole.PROCESS_ANALYST)
        mock_db_session.execute.return_value = _mock_scalar_result(analyst)

        token = _admin_token(analyst)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/admin/rotate-encryption-key",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_key_rotation_no_connections(self, test_app, mock_db_session: AsyncMock) -> None:
        """Admin with zero integration connections returns rotated=0, total=0."""
        admin = _make_user(UserRole.PLATFORM_ADMIN)

        # First execute returns the user for auth; second returns the empty list of connections
        mock_db_session.execute.side_effect = [
            _mock_scalar_result(admin),
            _mock_scalars_result([]),
        ]

        token = _admin_token(admin)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/admin/rotate-encryption-key",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["rotated"] == 0
        assert data["total"] == 0
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_key_rotation_with_connections(self, test_app, mock_db_session: AsyncMock) -> None:
        """Admin with integration connections triggers re-encryption for each."""
        from src.core.models import IntegrationConnection

        admin = _make_user(UserRole.PLATFORM_ADMIN)

        conn1 = MagicMock(spec=IntegrationConnection)
        conn1.encrypted_config = "old-cipher-1"
        conn2 = MagicMock(spec=IntegrationConnection)
        conn2.encrypted_config = "old-cipher-2"
        conn3 = MagicMock(spec=IntegrationConnection)
        conn3.encrypted_config = None  # No config — should not be counted

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(admin),
            _mock_scalars_result([conn1, conn2, conn3]),
        ]

        token = _admin_token(admin)

        with patch(
            "src.core.encryption.re_encrypt_value",
            return_value="new-cipher",
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/admin/rotate-encryption-key",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["rotated"] == 2  # conn3 has no config
        assert data["total"] == 3
        assert data["status"] == "completed"
        # Verify new values were set
        assert conn1.encrypted_config == "new-cipher"
        assert conn2.encrypted_config == "new-cipher"

    @pytest.mark.asyncio
    async def test_key_rotation_rollback_on_failure(self, test_app, mock_db_session: AsyncMock) -> None:
        """If re-encryption fails midway, session is rolled back and 500 is returned."""
        from src.core.models import IntegrationConnection

        admin = _make_user(UserRole.PLATFORM_ADMIN)

        conn = MagicMock(spec=IntegrationConnection)
        conn.encrypted_config = "cipher"

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(admin),
            _mock_scalars_result([conn]),
        ]

        token = _admin_token(admin)

        with patch(
            "src.core.encryption.re_encrypt_value",
            side_effect=ValueError("Decryption failed — wrong key"),
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/admin/rotate-encryption-key",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert response.status_code == 500
        mock_db_session.rollback.assert_awaited_once()
