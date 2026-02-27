"""BDD tests for Authentication and Authorization (OAuth2/OIDC + RBAC).

Story #313: Validate JWT authentication, role-based access control,
and engagement-scoped authorization for all five user roles.

Covers all 5 BDD acceptance criteria:
1. Valid OAuth2 bearer token authenticates the request
2. Expired token is rejected with 401
3. Process Analyst cannot access unassigned engagement data
4. Client Viewer cannot modify data (read-only access)
5. Engagement Lead has full access to their engagement
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.core.config import Settings
from src.core.models import User, UserRole
from src.core.permissions import (
    ROLE_PERMISSIONS,
    has_permission,
    has_role_level,
    require_engagement_access,
)


@pytest.fixture
def settings() -> Settings:
    """Create test settings with known secret key."""
    return Settings(
        jwt_secret_key="test-secret-key-for-unit-tests",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        jwt_refresh_token_expire_minutes=10080,
    )


def _make_user(
    role: UserRole = UserRole.PROCESS_ANALYST,
    *,
    user_id: uuid.UUID | None = None,
    is_active: bool = True,
) -> User:
    """Create a mock User with the given role."""
    user = MagicMock(spec=User)
    user.id = user_id or uuid.uuid4()
    user.email = f"test-{role.value}@example.com"
    user.name = f"Test {role.value}"
    user.role = role
    user.is_active = is_active
    return user


# ---------------------------------------------------------------------------
# Scenario 1: Valid OAuth2 bearer token authenticates the request
# ---------------------------------------------------------------------------


class TestValidTokenAuthentication:
    """Given a valid JWT bearer token, the request should be authenticated."""

    def test_valid_token_decodes_claims(self, settings: Settings) -> None:
        """Token claims (sub, email, role) are extractable after decode."""
        user_id = str(uuid.uuid4())
        token = create_access_token(
            {"sub": user_id, "email": "analyst@firm.com", "kmflow_role": "process_analyst"},
            settings=settings,
        )

        payload = decode_token(token, settings=settings)

        assert payload["sub"] == user_id
        assert payload["email"] == "analyst@firm.com"
        assert payload["kmflow_role"] == "process_analyst"

    def test_valid_token_has_access_type(self, settings: Settings) -> None:
        """Access tokens must have type=access claim."""
        token = create_access_token({"sub": str(uuid.uuid4())}, settings=settings)
        payload = decode_token(token, settings=settings)
        assert payload["type"] == "access"

    def test_valid_token_has_expiry(self, settings: Settings) -> None:
        """Token must contain exp claim for expiration."""
        token = create_access_token({"sub": str(uuid.uuid4())}, settings=settings)
        payload = decode_token(token, settings=settings)
        assert "exp" in payload

    def test_token_sub_maps_to_user_id(self, settings: Settings) -> None:
        """The sub claim should contain the user's UUID string."""
        uid = uuid.uuid4()
        token = create_access_token({"sub": str(uid)}, settings=settings)
        payload = decode_token(token, settings=settings)
        assert uuid.UUID(payload["sub"]) == uid

    def test_bearer_scheme_token_format(self, settings: Settings) -> None:
        """Token should be a dot-separated JWT string."""
        token = create_access_token({"sub": str(uuid.uuid4())}, settings=settings)
        parts = token.split(".")
        assert len(parts) == 3  # header.payload.signature

    def test_refresh_token_has_refresh_type(self, settings: Settings) -> None:
        """Refresh tokens must have type=refresh claim."""
        token = create_refresh_token({"sub": str(uuid.uuid4())}, settings=settings)
        payload = decode_token(token, settings=settings)
        assert payload["type"] == "refresh"


# ---------------------------------------------------------------------------
# Scenario 2: Expired token is rejected with 401
# ---------------------------------------------------------------------------


class TestExpiredTokenRejection:
    """Given an expired JWT, the response should be 401 with proper headers."""

    def test_expired_token_raises_401(self, settings: Settings) -> None:
        """Expired token should raise HTTPException with 401 status."""
        token = create_access_token(
            {"sub": str(uuid.uuid4())},
            settings=settings,
            expires_delta=timedelta(seconds=-10),
        )

        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, settings=settings)

        assert exc_info.value.status_code == 401

    def test_expired_token_includes_www_authenticate(self, settings: Settings) -> None:
        """Response should include WWW-Authenticate: Bearer header."""
        token = create_access_token(
            {"sub": str(uuid.uuid4())},
            settings=settings,
            expires_delta=timedelta(seconds=-10),
        )

        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, settings=settings)

        assert exc_info.value.headers is not None
        assert exc_info.value.headers.get("WWW-Authenticate") == "Bearer"

    def test_wrong_secret_raises_401(self, settings: Settings) -> None:
        """Token signed with wrong key should raise 401."""
        wrong_settings = Settings(
            jwt_secret_key="wrong-secret-key",
            jwt_algorithm="HS256",
        )
        token = create_access_token({"sub": str(uuid.uuid4())}, settings=wrong_settings)

        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, settings=settings)

        assert exc_info.value.status_code == 401

    def test_malformed_token_raises_401(self, settings: Settings) -> None:
        """Malformed JWT string should raise 401."""
        with pytest.raises(HTTPException) as exc_info:
            decode_token("not.a.valid.jwt.token", settings=settings)

        assert exc_info.value.status_code == 401

    def test_empty_token_raises_401(self, settings: Settings) -> None:
        """Empty token string should raise 401."""
        with pytest.raises(HTTPException) as exc_info:
            decode_token("", settings=settings)

        assert exc_info.value.status_code == 401

    def test_key_rotation_accepts_old_key(self) -> None:
        """Token signed with old key should be accepted when in rotation list."""
        old_key = "old-secret-key"
        new_key = "new-secret-key"

        old_settings = Settings(jwt_secret_key=old_key, jwt_algorithm="HS256")
        token = create_access_token({"sub": str(uuid.uuid4())}, settings=old_settings)

        # New settings with old key in rotation list
        rotation_settings = Settings(
            jwt_secret_key=new_key,
            jwt_secret_keys=f"{new_key},{old_key}",
            jwt_algorithm="HS256",
        )

        payload = decode_token(token, settings=rotation_settings)
        assert payload["type"] == "access"


# ---------------------------------------------------------------------------
# Scenario 3: Process Analyst cannot access unassigned engagement data
# ---------------------------------------------------------------------------


class TestProcessAnalystRestrictions:
    """Process Analyst should only access assigned engagements."""

    def test_analyst_has_evidence_read(self) -> None:
        """Process Analyst can read evidence."""
        user = _make_user(UserRole.PROCESS_ANALYST)
        assert has_permission(user, "evidence:read")

    def test_analyst_can_create_evidence(self) -> None:
        """Process Analyst can create evidence."""
        user = _make_user(UserRole.PROCESS_ANALYST)
        assert has_permission(user, "evidence:create")

    def test_analyst_cannot_delete_evidence(self) -> None:
        """Process Analyst cannot delete evidence."""
        user = _make_user(UserRole.PROCESS_ANALYST)
        assert not has_permission(user, "evidence:delete")

    def test_analyst_cannot_manage_team(self) -> None:
        """Process Analyst cannot manage engagement team."""
        user = _make_user(UserRole.PROCESS_ANALYST)
        assert not has_permission(user, "team:manage")

    def test_analyst_cannot_delete_engagement(self) -> None:
        """Process Analyst cannot delete an engagement."""
        user = _make_user(UserRole.PROCESS_ANALYST)
        assert not has_permission(user, "engagement:delete")

    @pytest.mark.asyncio
    async def test_analyst_denied_unassigned_engagement(self) -> None:
        """Analyst without membership should get 403 for engagement access."""
        user = _make_user(UserRole.PROCESS_ANALYST)
        engagement_id = uuid.uuid4()

        # Mock request with session factory that returns no membership
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        mock_factory = MagicMock()
        mock_factory().__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory().__aexit__ = AsyncMock(return_value=None)

        mock_request = MagicMock()
        mock_request.app.state.db_session_factory = mock_factory

        with pytest.raises(HTTPException) as exc_info:
            await require_engagement_access(engagement_id, mock_request, user)

        assert exc_info.value.status_code == 403
        assert "access" in exc_info.value.detail.lower()

    def test_analyst_can_generate_pov(self) -> None:
        """Process Analyst can generate POV views."""
        user = _make_user(UserRole.PROCESS_ANALYST)
        assert has_permission(user, "pov:generate")

    def test_analyst_cannot_configure_monitoring(self) -> None:
        """Process Analyst cannot configure monitoring (read-only)."""
        user = _make_user(UserRole.PROCESS_ANALYST)
        assert not has_permission(user, "monitoring:configure")


# ---------------------------------------------------------------------------
# Scenario 4: Client Viewer cannot modify data (read-only access)
# ---------------------------------------------------------------------------


class TestClientViewerReadOnly:
    """Client Viewer should have read-only access with no write permissions."""

    def test_client_viewer_can_read_engagement(self) -> None:
        """Client Viewer can read engagement data."""
        user = _make_user(UserRole.CLIENT_VIEWER)
        assert has_permission(user, "engagement:read")

    def test_client_viewer_can_read_pov(self) -> None:
        """Client Viewer can read POV views."""
        user = _make_user(UserRole.CLIENT_VIEWER)
        assert has_permission(user, "pov:read")

    def test_client_viewer_can_read_monitoring(self) -> None:
        """Client Viewer can read monitoring data."""
        user = _make_user(UserRole.CLIENT_VIEWER)
        assert has_permission(user, "monitoring:read")

    def test_client_viewer_cannot_create_evidence(self) -> None:
        """Client Viewer cannot create evidence."""
        user = _make_user(UserRole.CLIENT_VIEWER)
        assert not has_permission(user, "evidence:create")

    def test_client_viewer_cannot_update_evidence(self) -> None:
        """Client Viewer cannot update evidence."""
        user = _make_user(UserRole.CLIENT_VIEWER)
        assert not has_permission(user, "evidence:update")

    def test_client_viewer_cannot_delete_anything(self) -> None:
        """Client Viewer cannot delete any resource."""
        user = _make_user(UserRole.CLIENT_VIEWER)
        write_perms = [
            "evidence:create",
            "evidence:update",
            "evidence:delete",
            "engagement:create",
            "engagement:update",
            "engagement:delete",
            "pov:generate",
            "team:manage",
            "simulation:create",
            "simulation:run",
            "governance:write",
        ]
        for perm in write_perms:
            assert not has_permission(user, perm), f"Client viewer should not have {perm}"

    def test_client_viewer_cannot_query_copilot(self) -> None:
        """Client Viewer does not have copilot access."""
        user = _make_user(UserRole.CLIENT_VIEWER)
        assert not has_permission(user, "copilot:query")

    def test_client_viewer_lowest_role_level(self) -> None:
        """Client Viewer is the lowest role in hierarchy."""
        user = _make_user(UserRole.CLIENT_VIEWER)
        assert has_role_level(user, UserRole.CLIENT_VIEWER)
        assert not has_role_level(user, UserRole.EVIDENCE_REVIEWER)


# ---------------------------------------------------------------------------
# Scenario 5: Engagement Lead has full access to their engagement
# ---------------------------------------------------------------------------


class TestEngagementLeadFullAccess:
    """Engagement Lead should have full access within their engagement."""

    def test_lead_has_all_engagement_permissions(self) -> None:
        """Engagement Lead should have all engagement CRUD permissions."""
        user = _make_user(UserRole.ENGAGEMENT_LEAD)
        assert has_permission(user, "engagement:create")
        assert has_permission(user, "engagement:read")
        assert has_permission(user, "engagement:update")
        assert has_permission(user, "engagement:delete")

    def test_lead_has_all_evidence_permissions(self) -> None:
        """Engagement Lead should have full evidence access."""
        user = _make_user(UserRole.ENGAGEMENT_LEAD)
        assert has_permission(user, "evidence:create")
        assert has_permission(user, "evidence:read")
        assert has_permission(user, "evidence:update")
        assert has_permission(user, "evidence:delete")

    def test_lead_can_manage_team(self) -> None:
        """Engagement Lead can manage team members."""
        user = _make_user(UserRole.ENGAGEMENT_LEAD)
        assert has_permission(user, "team:manage")

    def test_lead_can_manage_monitoring(self) -> None:
        """Engagement Lead can configure and manage monitoring."""
        user = _make_user(UserRole.ENGAGEMENT_LEAD)
        assert has_permission(user, "monitoring:configure")
        assert has_permission(user, "monitoring:manage")
        assert has_permission(user, "monitoring:read")

    def test_lead_can_manage_simulations(self) -> None:
        """Engagement Lead has full simulation access."""
        user = _make_user(UserRole.ENGAGEMENT_LEAD)
        assert has_permission(user, "simulation:create")
        assert has_permission(user, "simulation:run")
        assert has_permission(user, "simulation:read")

    def test_lead_can_manage_governance(self) -> None:
        """Engagement Lead can read and write governance data."""
        user = _make_user(UserRole.ENGAGEMENT_LEAD)
        assert has_permission(user, "governance:read")
        assert has_permission(user, "governance:write")

    def test_lead_exceeds_analyst_role_level(self) -> None:
        """Engagement Lead is above Process Analyst in hierarchy."""
        user = _make_user(UserRole.ENGAGEMENT_LEAD)
        assert has_role_level(user, UserRole.PROCESS_ANALYST)
        assert has_role_level(user, UserRole.EVIDENCE_REVIEWER)
        assert has_role_level(user, UserRole.CLIENT_VIEWER)

    @pytest.mark.asyncio
    async def test_platform_admin_bypasses_engagement_check(self) -> None:
        """Platform Admin bypasses engagement membership verification."""
        user = _make_user(UserRole.PLATFORM_ADMIN)
        engagement_id = uuid.uuid4()

        mock_request = MagicMock()

        # Should return user without checking DB
        result = await require_engagement_access(engagement_id, mock_request, user)

        assert result == user
        # Session factory should not have been called (admin bypass)
        mock_request.app.state.db_session_factory.assert_not_called()


# ---------------------------------------------------------------------------
# Evidence Reviewer role boundary tests
# ---------------------------------------------------------------------------


class TestEvidenceReviewerBoundaries:
    """Evidence Reviewer has read + validate permissions only."""

    def test_reviewer_can_read_evidence(self) -> None:
        """Evidence Reviewer can read evidence."""
        user = _make_user(UserRole.EVIDENCE_REVIEWER)
        assert has_permission(user, "evidence:read")

    def test_reviewer_can_validate_evidence(self) -> None:
        """Evidence Reviewer can validate evidence."""
        user = _make_user(UserRole.EVIDENCE_REVIEWER)
        assert has_permission(user, "evidence:validate")

    def test_reviewer_cannot_create_evidence(self) -> None:
        """Evidence Reviewer cannot create new evidence."""
        user = _make_user(UserRole.EVIDENCE_REVIEWER)
        assert not has_permission(user, "evidence:create")

    def test_reviewer_cannot_generate_pov(self) -> None:
        """Evidence Reviewer cannot generate POV views."""
        user = _make_user(UserRole.EVIDENCE_REVIEWER)
        assert not has_permission(user, "pov:generate")


# ---------------------------------------------------------------------------
# Cross-role permission completeness
# ---------------------------------------------------------------------------


class TestRolePermissionCompleteness:
    """Verify the permission matrix is complete and well-structured."""

    def test_all_roles_have_permission_entries(self) -> None:
        """Every UserRole should have an entry in ROLE_PERMISSIONS."""
        for role in UserRole:
            assert role.value in ROLE_PERMISSIONS, f"Missing permissions for {role.value}"

    def test_admin_has_wildcard_only(self) -> None:
        """Platform admin should have exactly ['*'] (wildcard)."""
        assert ROLE_PERMISSIONS["platform_admin"] == ["*"]

    def test_role_hierarchy_permission_counts(self) -> None:
        """Higher roles should have more total permissions than lower roles."""
        lead_count = len(ROLE_PERMISSIONS["engagement_lead"])
        analyst_count = len(ROLE_PERMISSIONS["process_analyst"])
        reviewer_count = len(ROLE_PERMISSIONS["evidence_reviewer"])
        viewer_count = len(ROLE_PERMISSIONS["client_viewer"])

        # Engagement lead has the most permissions (excluding admin wildcard)
        assert lead_count > analyst_count, "Lead should have more perms than analyst"
        assert lead_count > reviewer_count, "Lead should have more perms than reviewer"
        assert lead_count > viewer_count, "Lead should have more perms than viewer"
        # Viewer has the fewest
        assert viewer_count < analyst_count, "Viewer should have fewer perms than analyst"

    def test_no_empty_permission_lists(self) -> None:
        """No role should have an empty permission list."""
        for role, perms in ROLE_PERMISSIONS.items():
            assert len(perms) > 0, f"{role} has empty permission list"


# ---------------------------------------------------------------------------
# Token edge cases
# ---------------------------------------------------------------------------


class TestTokenEdgeCases:
    """Edge cases for token validation."""

    def test_token_with_custom_claims_preserved(self, settings: Settings) -> None:
        """Custom claims in token should be preserved after decode."""
        custom_data = {
            "sub": str(uuid.uuid4()),
            "email": "user@example.com",
            "kmflow_role": "engagement_lead",
            "engagement_ids": ["eng-1", "eng-2"],
        }
        token = create_access_token(custom_data, settings=settings)
        payload = decode_token(token, settings=settings)

        assert payload["email"] == "user@example.com"
        assert payload["kmflow_role"] == "engagement_lead"
        assert payload["engagement_ids"] == ["eng-1", "eng-2"]

    def test_access_and_refresh_tokens_differ(self, settings: Settings) -> None:
        """Access and refresh tokens should be different strings."""
        data = {"sub": str(uuid.uuid4())}
        access = create_access_token(data, settings=settings)
        refresh = create_refresh_token(data, settings=settings)
        assert access != refresh

    def test_token_not_valid_before_creation(self, settings: Settings) -> None:
        """Token should contain exp > current time (not already expired)."""
        token = create_access_token({"sub": str(uuid.uuid4())}, settings=settings)
        payload = decode_token(token, settings=settings)
        assert payload["exp"] > datetime.now(UTC).timestamp()
