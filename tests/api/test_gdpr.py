"""Tests for GDPR data subject rights endpoints (Issue #165).

Covers:
- Data export returns the requesting user's data from all tables
- Data export does NOT return another user's data
- Erasure request sets erasure_requested_at / erasure_scheduled_at
- Admin anonymize endpoint anonymises user fields and audit_logs actor
- Non-admin cannot call admin anonymise
- Consent GET returns empty list for a new user
- Consent POST stores a consent record
- Consent POST: grant then revoke cycle works correctly
- Consent POST rejects an invalid consent_type
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from src.core.models import (
    Annotation,
    AuditAction,
    AuditLog,
    EngagementMember,
    User,
    UserConsent,
    UserRole,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    user_id: uuid.UUID | None = None,
    email: str = "alice@example.com",
    name: str = "Alice",
    role: UserRole = UserRole.PROCESS_ANALYST,
    is_active: bool = True,
) -> MagicMock:
    """Return a MagicMock that quacks like a User ORM object."""
    u = MagicMock(spec=User)
    u.id = user_id or uuid.uuid4()
    u.email = email
    u.name = name
    u.role = role
    u.is_active = is_active
    u.external_id = None
    u.hashed_password = None
    u.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    u.updated_at = datetime(2025, 1, 2, tzinfo=UTC)
    u.erasure_requested_at = None
    u.erasure_scheduled_at = None
    return u


def _make_member(user_id: uuid.UUID, engagement_id: uuid.UUID | None = None) -> MagicMock:
    m = MagicMock(spec=EngagementMember)
    m.id = uuid.uuid4()
    m.engagement_id = engagement_id or uuid.uuid4()
    m.user_id = user_id
    m.role_in_engagement = "member"
    m.added_at = datetime(2025, 2, 1, tzinfo=UTC)
    return m


def _make_audit(actor_str: str) -> MagicMock:
    a = MagicMock(spec=AuditLog)
    a.id = uuid.uuid4()
    a.engagement_id = uuid.uuid4()
    a.action = AuditAction.LOGIN
    a.actor = actor_str
    a.details = "test audit entry"
    a.created_at = datetime(2025, 3, 1, tzinfo=UTC)
    return a


def _make_annotation(author_id_str: str) -> MagicMock:
    ann = MagicMock(spec=Annotation)
    ann.id = uuid.uuid4()
    ann.engagement_id = uuid.uuid4()
    ann.target_type = "process_element"
    ann.target_id = "elem-1"
    ann.author_id = author_id_str
    ann.content = "This is a test annotation."
    ann.created_at = datetime(2025, 4, 1, tzinfo=UTC)
    ann.updated_at = datetime(2025, 4, 2, tzinfo=UTC)
    return ann


def _make_consent(
    user_id: uuid.UUID,
    consent_type: str = "analytics",
    granted: bool = True,
    revoked_at: datetime | None = None,
) -> MagicMock:
    c = MagicMock(spec=UserConsent)
    c.id = uuid.uuid4()
    c.user_id = user_id
    c.consent_type = consent_type
    c.granted = granted
    c.granted_at = datetime(2025, 5, 1, tzinfo=UTC)
    c.revoked_at = revoked_at
    c.ip_address = "127.0.0.1"
    return c


def _scalars_result(items: list) -> MagicMock:
    """Mock result whose .scalars().all() returns items."""
    scalars = MagicMock()
    scalars.all.return_value = items
    r = MagicMock()
    r.scalars.return_value = scalars
    return r


def _scalar_one_result(value) -> MagicMock:  # noqa: ANN001
    """Mock result whose .scalar_one_or_none() returns value."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


# ---------------------------------------------------------------------------
# Data Export
# ---------------------------------------------------------------------------


class TestDataExport:
    """GET /api/v1/gdpr/export"""

    @pytest.mark.asyncio
    async def test_export_returns_current_user_data(
        self, client: AsyncClient, mock_db_session: AsyncMock, test_app
    ) -> None:
        """Export should collect and return the authenticated user's data."""
        from src.core.auth import get_current_user

        user_id = uuid.uuid4()
        mock_user = _make_user(user_id=user_id)

        # Override current user
        test_app.dependency_overrides[get_current_user] = lambda: mock_user

        member = _make_member(user_id)
        audit = _make_audit(str(user_id))
        annotation = _make_annotation(str(user_id))

        # Execute is called three times: members, audit_logs, annotations
        mock_db_session.execute = AsyncMock(
            side_effect=[
                _scalars_result([member]),
                _scalars_result([audit]),
                _scalars_result([annotation]),
            ]
        )

        response = await client.get("/api/v1/gdpr/export")
        assert response.status_code == 200

        data = response.json()
        assert "user_profile" in data
        assert data["user_profile"]["id"] == str(user_id)
        assert data["user_profile"]["email"] == mock_user.email

        assert len(data["memberships"]) == 1
        assert data["memberships"][0]["user_id"] == str(user_id)

        assert len(data["audit_entries"]) == 1
        assert data["audit_entries"][0]["actor"] == str(user_id)

        assert len(data["annotations"]) == 1
        assert data["annotations"][0]["author_id"] == str(user_id)

    @pytest.mark.asyncio
    async def test_export_does_not_return_other_users_data(
        self, client: AsyncClient, mock_db_session: AsyncMock, test_app
    ) -> None:
        """Export should only return data for the authenticated user, not other users."""
        from src.core.auth import get_current_user

        user_id = uuid.uuid4()
        other_user_id = uuid.uuid4()
        mock_user = _make_user(user_id=user_id)

        test_app.dependency_overrides[get_current_user] = lambda: mock_user

        # Simulate DB returning empty results (i.e., no other-user data leaks in)
        mock_db_session.execute = AsyncMock(
            side_effect=[
                _scalars_result([]),   # memberships
                _scalars_result([]),   # audit_logs
                _scalars_result([]),   # annotations
            ]
        )

        response = await client.get("/api/v1/gdpr/export")
        assert response.status_code == 200

        data = response.json()
        # Should not contain any records for the other user
        assert all(m["user_id"] != str(other_user_id) for m in data["memberships"])
        assert all(e["actor"] != str(other_user_id) for e in data["audit_entries"])
        assert all(a["author_id"] != str(other_user_id) for a in data["annotations"])


# ---------------------------------------------------------------------------
# Erasure Request
# ---------------------------------------------------------------------------


class TestErasureRequest:
    """POST /api/v1/gdpr/erasure-request"""

    @pytest.mark.asyncio
    async def test_erasure_request_sets_scheduled_date(
        self, client: AsyncClient, mock_db_session: AsyncMock, test_app
    ) -> None:
        """Erasure request should set erasure_requested_at and erasure_scheduled_at."""
        from src.core.auth import get_current_user

        user_id = uuid.uuid4()
        mock_user = _make_user(user_id=user_id)

        # The route re-fetches the user inside its own session execution
        db_user = _make_user(user_id=user_id)
        db_user.erasure_requested_at = None
        db_user.erasure_scheduled_at = None

        test_app.dependency_overrides[get_current_user] = lambda: mock_user
        mock_db_session.execute = AsyncMock(return_value=_scalar_one_result(db_user))

        # Simulate refresh setting the timestamps back on the object
        now = datetime.now(UTC)
        grace = timedelta(days=30)

        def _refresh(obj):  # noqa: ANN001
            if obj is db_user:
                obj.erasure_requested_at = now
                obj.erasure_scheduled_at = now + grace

        mock_db_session.refresh = AsyncMock(side_effect=_refresh)

        response = await client.post("/api/v1/gdpr/erasure-request")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == str(user_id)
        assert data["erasure_requested_at"] is not None
        assert data["erasure_scheduled_at"] is not None
        assert "scheduled for erasure" in data["message"]

        # Verify the fields were actually set on the object
        assert db_user.erasure_requested_at is not None
        assert db_user.erasure_scheduled_at is not None
        mock_db_session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# Admin Anonymize
# ---------------------------------------------------------------------------


class TestAdminAnonymize:
    """POST /api/v1/gdpr/admin/anonymize/{user_id}"""

    @pytest.mark.asyncio
    async def test_admin_can_anonymize_user(
        self, client: AsyncClient, mock_db_session: AsyncMock, test_app
    ) -> None:
        """Platform admin should be able to immediately anonymise a user."""
        from src.core.auth import get_current_user

        admin_user = _make_user(role=UserRole.PLATFORM_ADMIN, email="admin@kmflow.dev")
        target_id = uuid.uuid4()
        target_user = _make_user(user_id=target_id, email="victim@example.com", name="Real Name")

        test_app.dependency_overrides[get_current_user] = lambda: admin_user
        mock_db_session.execute = AsyncMock(return_value=_scalar_one_result(target_user))

        response = await client.post(f"/api/v1/gdpr/admin/anonymize/{target_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == str(target_id)
        assert "anonymised" in data["message"]

        # Verify the user object was mutated
        assert target_user.name == "Deleted User"
        assert target_user.email.startswith("deleted-")
        assert target_user.email.endswith("@anonymized.local")
        assert target_user.is_active is False
        assert target_user.hashed_password is None
        assert target_user.external_id is None

        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_admin_cannot_anonymize(
        self, client: AsyncClient, mock_db_session: AsyncMock, test_app
    ) -> None:
        """A non-admin user must receive 403 when attempting to anonymise."""
        from src.core.auth import get_current_user

        non_admin = _make_user(role=UserRole.PROCESS_ANALYST)
        test_app.dependency_overrides[get_current_user] = lambda: non_admin

        target_id = uuid.uuid4()
        response = await client.post(f"/api/v1/gdpr/admin/anonymize/{target_id}")
        assert response.status_code == 403
        assert "platform admins" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_admin_anonymize_returns_404_for_unknown_user(
        self, client: AsyncClient, mock_db_session: AsyncMock, test_app
    ) -> None:
        """Admin anonymise should return 404 when the target user does not exist."""
        from src.core.auth import get_current_user

        admin_user = _make_user(role=UserRole.PLATFORM_ADMIN)
        test_app.dependency_overrides[get_current_user] = lambda: admin_user
        mock_db_session.execute = AsyncMock(return_value=_scalar_one_result(None))

        target_id = uuid.uuid4()
        response = await client.post(f"/api/v1/gdpr/admin/anonymize/{target_id}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Consent GET
# ---------------------------------------------------------------------------


class TestConsentGet:
    """GET /api/v1/gdpr/consent"""

    @pytest.mark.asyncio
    async def test_consent_get_returns_empty_for_new_user(
        self, client: AsyncClient, mock_db_session: AsyncMock, test_app
    ) -> None:
        """A user with no consent records should receive an empty consents list."""
        from src.core.auth import get_current_user

        user_id = uuid.uuid4()
        mock_user = _make_user(user_id=user_id)
        test_app.dependency_overrides[get_current_user] = lambda: mock_user

        # No consent rows in DB
        mock_db_session.execute = AsyncMock(return_value=_scalars_result([]))

        response = await client.get("/api/v1/gdpr/consent")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == str(user_id)
        assert data["consents"] == []

    @pytest.mark.asyncio
    async def test_consent_get_returns_latest_per_type(
        self, client: AsyncClient, mock_db_session: AsyncMock, test_app
    ) -> None:
        """Only the most recent consent event per type should be returned."""
        from src.core.auth import get_current_user

        user_id = uuid.uuid4()
        mock_user = _make_user(user_id=user_id)
        test_app.dependency_overrides[get_current_user] = lambda: mock_user

        # Two analytics consent rows — the first (index 0) is the most recent
        # because the query orders by granted_at DESC.
        older_analytics = _make_consent(user_id, "analytics", granted=True)
        newer_analytics = _make_consent(user_id, "analytics", granted=False)
        newer_analytics.granted_at = datetime(2025, 6, 1, tzinfo=UTC)

        mock_db_session.execute = AsyncMock(
            return_value=_scalars_result([newer_analytics, older_analytics])
        )

        response = await client.get("/api/v1/gdpr/consent")
        assert response.status_code == 200

        data = response.json()
        assert len(data["consents"]) == 1
        assert data["consents"][0]["consent_type"] == "analytics"
        assert data["consents"][0]["granted"] is False  # Most recent row wins


# ---------------------------------------------------------------------------
# Consent POST
# ---------------------------------------------------------------------------


class TestConsentPost:
    """POST /api/v1/gdpr/consent"""

    @pytest.mark.asyncio
    async def test_consent_post_stores_consent(
        self, client: AsyncClient, mock_db_session: AsyncMock, test_app
    ) -> None:
        """Posting a consent update should commit a new UserConsent row."""
        from src.core.auth import get_current_user

        user_id = uuid.uuid4()
        mock_user = _make_user(user_id=user_id)
        test_app.dependency_overrides[get_current_user] = lambda: mock_user

        # After the POST, get_consent_status is called internally which
        # does a DB query. Return a single consent row representing the
        # freshly inserted record.
        stored_consent = _make_consent(user_id, "analytics", granted=True)
        mock_db_session.execute = AsyncMock(return_value=_scalars_result([stored_consent]))

        payload = {"consent_type": "analytics", "granted": True}
        response = await client.post("/api/v1/gdpr/consent", json=payload)
        assert response.status_code == 200

        # session.add must have been called with a UserConsent object
        add_calls = mock_db_session.add.call_args_list
        assert len(add_calls) >= 1
        added_obj = add_calls[0][0][0]
        assert isinstance(added_obj, UserConsent)
        assert added_obj.consent_type == "analytics"
        assert added_obj.granted is True

        mock_db_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_consent_post_grant_then_revoke(
        self, client: AsyncClient, mock_db_session: AsyncMock, test_app
    ) -> None:
        """Revoking a previously granted consent should create a new row with granted=False."""
        from src.core.auth import get_current_user

        user_id = uuid.uuid4()
        mock_user = _make_user(user_id=user_id)
        test_app.dependency_overrides[get_current_user] = lambda: mock_user

        revoked_consent = _make_consent(
            user_id,
            "data_processing",
            granted=False,
            revoked_at=datetime(2025, 6, 15, tzinfo=UTC),
        )
        mock_db_session.execute = AsyncMock(return_value=_scalars_result([revoked_consent]))

        payload = {"consent_type": "data_processing", "granted": False}
        response = await client.post("/api/v1/gdpr/consent", json=payload)
        assert response.status_code == 200

        # Verify what was added
        add_calls = mock_db_session.add.call_args_list
        assert len(add_calls) >= 1
        added_obj = add_calls[0][0][0]
        assert isinstance(added_obj, UserConsent)
        assert added_obj.consent_type == "data_processing"
        assert added_obj.granted is False
        # revoked_at should be set when revoking
        assert added_obj.revoked_at is not None

    @pytest.mark.asyncio
    async def test_consent_post_rejects_invalid_type(
        self, client: AsyncClient, mock_db_session: AsyncMock, test_app
    ) -> None:
        """An unknown consent_type must be rejected with 422."""
        from src.core.auth import get_current_user

        mock_user = _make_user()
        test_app.dependency_overrides[get_current_user] = lambda: mock_user

        payload = {"consent_type": "not_a_real_consent_type", "granted": True}
        response = await client.post("/api/v1/gdpr/consent", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_consent_post_all_valid_types(
        self, client: AsyncClient, mock_db_session: AsyncMock, test_app
    ) -> None:
        """All three valid consent types should be accepted."""
        from src.core.auth import get_current_user

        user_id = uuid.uuid4()
        mock_user = _make_user(user_id=user_id)
        test_app.dependency_overrides[get_current_user] = lambda: mock_user

        valid_types = ["analytics", "data_processing", "marketing_communications"]
        for consent_type in valid_types:
            mock_db_session.add.reset_mock()
            mock_db_session.commit.reset_mock()
            stored = _make_consent(user_id, consent_type, granted=True)
            mock_db_session.execute = AsyncMock(return_value=_scalars_result([stored]))

            payload = {"consent_type": consent_type, "granted": True}
            response = await client.post("/api/v1/gdpr/consent", json=payload)
            assert response.status_code == 200, f"Expected 200 for consent_type={consent_type}"
