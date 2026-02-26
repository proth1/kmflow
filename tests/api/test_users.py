"""Tests for user management and engagement membership routes.

Covers:
- POST /api/v1/users (create user)
- GET  /api/v1/users (list users)
- GET  /api/v1/users/{id} (get user)
- PATCH /api/v1/users/{id} (update user)
- POST /api/v1/engagements/{id}/members (add member)
- DELETE /api/v1/engagements/{id}/members/{uid} (remove member)
- GET  /api/v1/engagements/{id}/members (list members)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.auth import create_access_token, get_current_user, hash_password
from src.core.config import Settings
from src.core.models import Engagement, EngagementMember, EngagementStatus, User, UserRole


@pytest.fixture(autouse=True)
def _restore_real_auth(test_app):
    """Remove the global get_current_user override so user tests use real JWT flow."""
    test_app.dependency_overrides.pop(get_current_user, None)
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _test_settings() -> Settings:
    return Settings(
        jwt_secret_key="test-secret-key-for-tests",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        auth_dev_mode=True,
    )


def _make_admin() -> User:
    """Create a platform admin User."""
    return User(
        id=uuid.uuid4(),
        email="admin@example.com",
        name="Admin User",
        role=UserRole.PLATFORM_ADMIN,
        is_active=True,
        hashed_password=hash_password("adminpass"),
    )


def _make_lead() -> User:
    """Create an engagement lead User."""
    return User(
        id=uuid.uuid4(),
        email="lead@example.com",
        name="Lead User",
        role=UserRole.ENGAGEMENT_LEAD,
        is_active=True,
    )


def _make_analyst() -> User:
    """Create a process analyst User."""
    return User(
        id=uuid.uuid4(),
        email="analyst@example.com",
        name="Analyst User",
        role=UserRole.PROCESS_ANALYST,
        is_active=True,
    )


def _make_engagement() -> Engagement:
    """Create a test Engagement."""
    return Engagement(
        id=uuid.uuid4(),
        name="Test Engagement",
        client="Test Client",
        business_area="Finance",
        status=EngagementStatus.ACTIVE,
    )


def _auth_header(user: User) -> dict[str, str]:
    """Build an Authorization header for the given user."""
    settings = _test_settings()
    token = create_access_token({"sub": str(user.id)}, settings)
    return {"Authorization": f"Bearer {token}"}


def _mock_scalar_result(value):  # noqa: ANN001, ANN202
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalars_result(items: list) -> MagicMock:
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result = MagicMock()
    result.scalars.return_value = scalars_mock
    return result


def _mock_count_result(count: int) -> MagicMock:
    result = MagicMock()
    result.scalar.return_value = count
    return result


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


class TestCreateUser:
    """POST /api/v1/users"""

    @pytest.mark.asyncio
    async def test_admin_can_create_user(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Admin should be able to create a new user."""
        admin = _make_admin()
        # First call: get_current_user fetches the admin
        # Second call: check duplicate email
        mock_db_session.execute.side_effect = [
            _mock_scalar_result(admin),  # get_current_user
            _mock_scalar_result(None),  # no duplicate
        ]

        response = await client.post(
            "/api/v1/users",
            json={"email": "new@example.com", "name": "New User", "role": "process_analyst", "password": "securepass1"},
            headers=_auth_header(admin),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "new@example.com"
        assert data["role"] == "process_analyst"

    @pytest.mark.asyncio
    async def test_non_admin_cannot_create_user(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Non-admin should get 403."""
        analyst = _make_analyst()
        mock_db_session.execute.return_value = _mock_scalar_result(analyst)

        response = await client.post(
            "/api/v1/users",
            json={"email": "new@example.com", "name": "New User"},
            headers=_auth_header(analyst),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_duplicate_email_returns_409(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 409 for duplicate email."""
        admin = _make_admin()
        existing = _make_analyst()
        mock_db_session.execute.side_effect = [
            _mock_scalar_result(admin),  # get_current_user
            _mock_scalar_result(existing),  # duplicate found
        ]

        response = await client.post(
            "/api/v1/users",
            json={"email": "analyst@example.com", "name": "Dup User"},
            headers=_auth_header(admin),
        )
        assert response.status_code == 409


class TestListUsers:
    """GET /api/v1/users"""

    @pytest.mark.asyncio
    async def test_admin_can_list_users(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Admin should see paginated user list."""
        admin = _make_admin()
        analyst = _make_analyst()
        mock_db_session.execute.side_effect = [
            _mock_scalar_result(admin),  # get_current_user
            _mock_scalars_result([admin, analyst]),
            _mock_count_result(2),
        ]

        response = await client.get("/api/v1/users", headers=_auth_header(admin))
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_non_admin_cannot_list_users(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Non-admin should get 403."""
        analyst = _make_analyst()
        mock_db_session.execute.return_value = _mock_scalar_result(analyst)

        response = await client.get("/api/v1/users", headers=_auth_header(analyst))
        assert response.status_code == 403


class TestGetUser:
    """GET /api/v1/users/{id}"""

    @pytest.mark.asyncio
    async def test_get_user_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return user when found."""
        admin = _make_admin()
        analyst = _make_analyst()
        mock_db_session.execute.side_effect = [
            _mock_scalar_result(admin),  # get_current_user
            _mock_scalar_result(analyst),  # get user
        ]

        response = await client.get(f"/api/v1/users/{analyst.id}", headers=_auth_header(admin))
        assert response.status_code == 200
        assert response.json()["email"] == "analyst@example.com"

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 for nonexistent user."""
        admin = _make_admin()
        mock_db_session.execute.side_effect = [
            _mock_scalar_result(admin),  # get_current_user
            _mock_scalar_result(None),  # not found
        ]

        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/users/{fake_id}", headers=_auth_header(admin))
        assert response.status_code == 404


class TestUpdateUser:
    """PATCH /api/v1/users/{id}"""

    @pytest.mark.asyncio
    async def test_admin_can_update_user(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Admin should be able to update user fields."""
        admin = _make_admin()
        analyst = _make_analyst()
        mock_db_session.execute.side_effect = [
            _mock_scalar_result(admin),  # get_current_user
            _mock_scalar_result(analyst),  # get user to update
        ]

        response = await client.patch(
            f"/api/v1/users/{analyst.id}",
            json={"name": "Updated Name"},
            headers=_auth_header(admin),
        )
        assert response.status_code == 200
        assert analyst.name == "Updated Name"

    @pytest.mark.asyncio
    async def test_non_admin_cannot_update_user(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Non-admin should get 403."""
        analyst = _make_analyst()
        mock_db_session.execute.return_value = _mock_scalar_result(analyst)

        response = await client.patch(
            f"/api/v1/users/{analyst.id}",
            json={"name": "Nope"},
            headers=_auth_header(analyst),
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Engagement membership
# ---------------------------------------------------------------------------


class TestAddEngagementMember:
    """POST /api/v1/engagements/{id}/members"""

    @pytest.mark.asyncio
    async def test_lead_can_add_member(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Engagement lead should be able to add a member."""
        lead = _make_lead()
        analyst = _make_analyst()
        engagement = _make_engagement()
        lead_membership = EngagementMember(
            id=uuid.uuid4(),
            engagement_id=engagement.id,
            user_id=lead.id,
            role_in_engagement="lead",
        )

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(lead),  # get_current_user
            _mock_scalar_result(lead_membership),  # require_engagement_access membership check
            _mock_scalar_result(engagement),  # engagement exists
            _mock_scalar_result(analyst),  # user exists
            _mock_scalar_result(None),  # no existing membership
        ]

        response = await client.post(
            f"/api/v1/engagements/{engagement.id}/members",
            json={"user_id": str(analyst.id), "role_in_engagement": "analyst"},
            headers=_auth_header(lead),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == str(analyst.id)
        assert data["role_in_engagement"] == "analyst"

    @pytest.mark.asyncio
    async def test_analyst_cannot_add_member(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Process analyst should not be able to manage team."""
        analyst = _make_analyst()
        mock_db_session.execute.return_value = _mock_scalar_result(analyst)

        response = await client.post(
            f"/api/v1/engagements/{uuid.uuid4()}/members",
            json={"user_id": str(uuid.uuid4()), "role_in_engagement": "member"},
            headers=_auth_header(analyst),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_duplicate_membership_returns_409(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 409 for duplicate membership."""
        lead = _make_lead()
        analyst = _make_analyst()
        engagement = _make_engagement()
        lead_membership = EngagementMember(
            id=uuid.uuid4(),
            engagement_id=engagement.id,
            user_id=lead.id,
            role_in_engagement="lead",
        )
        existing_member = EngagementMember(
            id=uuid.uuid4(),
            engagement_id=engagement.id,
            user_id=analyst.id,
            role_in_engagement="member",
        )

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(lead),  # get_current_user
            _mock_scalar_result(lead_membership),  # require_engagement_access membership check
            _mock_scalar_result(engagement),  # engagement exists
            _mock_scalar_result(analyst),  # user exists
            _mock_scalar_result(existing_member),  # already a member
        ]

        response = await client.post(
            f"/api/v1/engagements/{engagement.id}/members",
            json={"user_id": str(analyst.id), "role_in_engagement": "member"},
            headers=_auth_header(lead),
        )
        assert response.status_code == 409


class TestRemoveEngagementMember:
    """DELETE /api/v1/engagements/{id}/members/{uid}"""

    @pytest.mark.asyncio
    async def test_lead_can_remove_member(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Engagement lead should be able to remove a member."""
        lead = _make_lead()
        analyst = _make_analyst()
        engagement = _make_engagement()
        lead_membership = EngagementMember(
            id=uuid.uuid4(),
            engagement_id=engagement.id,
            user_id=lead.id,
            role_in_engagement="lead",
        )
        member = EngagementMember(
            id=uuid.uuid4(),
            engagement_id=engagement.id,
            user_id=analyst.id,
            role_in_engagement="member",
        )

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(lead),  # get_current_user
            _mock_scalar_result(lead_membership),  # require_engagement_access membership check
            _mock_scalar_result(member),  # membership found
        ]
        mock_db_session.delete = AsyncMock()

        response = await client.delete(
            f"/api/v1/engagements/{engagement.id}/members/{analyst.id}",
            headers=_auth_header(lead),
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_remove_nonexistent_member_returns_404(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 when membership doesn't exist."""
        lead = _make_lead()
        lead_membership = EngagementMember(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            user_id=lead.id,
            role_in_engagement="lead",
        )
        mock_db_session.execute.side_effect = [
            _mock_scalar_result(lead),  # get_current_user
            _mock_scalar_result(lead_membership),  # require_engagement_access membership check
            _mock_scalar_result(None),  # membership not found
        ]

        response = await client.delete(
            f"/api/v1/engagements/{uuid.uuid4()}/members/{uuid.uuid4()}",
            headers=_auth_header(lead),
        )
        assert response.status_code == 404


class TestListEngagementMembers:
    """GET /api/v1/engagements/{id}/members"""

    @pytest.mark.asyncio
    async def test_list_members(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return list of engagement members."""
        admin = _make_admin()
        engagement = _make_engagement()
        member = EngagementMember(
            id=uuid.uuid4(),
            engagement_id=engagement.id,
            user_id=admin.id,
            role_in_engagement="lead",
        )

        mock_db_session.execute.side_effect = [
            _mock_scalar_result(admin),  # get_current_user
            _mock_scalar_result(engagement),  # engagement exists
            _mock_scalars_result([member]),  # members
        ]

        response = await client.get(
            f"/api/v1/engagements/{engagement.id}/members",
            headers=_auth_header(admin),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["role_in_engagement"] == "lead"

    @pytest.mark.asyncio
    async def test_list_members_engagement_not_found(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """Should return 404 when engagement doesn't exist."""
        admin = _make_admin()
        mock_db_session.execute.side_effect = [
            _mock_scalar_result(admin),  # get_current_user
            _mock_scalar_result(None),  # engagement not found
        ]

        response = await client.get(
            f"/api/v1/engagements/{uuid.uuid4()}/members",
            headers=_auth_header(admin),
        )
        assert response.status_code == 404
