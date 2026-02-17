"""Tests for the RBAC permissions module (src/core/permissions.py).

Covers permission checking, role hierarchy, and the permission matrix.
"""

from __future__ import annotations

import uuid

from src.core.models import User, UserRole
from src.core.permissions import (
    ROLE_HIERARCHY,
    ROLE_PERMISSIONS,
    has_permission,
    has_role_level,
)


def _make_user(role: UserRole = UserRole.PROCESS_ANALYST, **kwargs) -> User:  # noqa: ANN003
    """Create a test User object with the given role."""
    defaults = {
        "id": uuid.uuid4(),
        "email": "test@example.com",
        "name": "Test User",
        "role": role,
        "is_active": True,
    }
    defaults.update(kwargs)
    return User(**defaults)


# ---------------------------------------------------------------------------
# Permission matrix
# ---------------------------------------------------------------------------


class TestPermissionMatrix:
    """Test the ROLE_PERMISSIONS mapping."""

    def test_platform_admin_has_wildcard(self) -> None:
        """Platform admin should have '*' (all permissions)."""
        assert "*" in ROLE_PERMISSIONS["platform_admin"]

    def test_engagement_lead_has_team_manage(self) -> None:
        """Engagement lead should have team:manage permission."""
        assert "team:manage" in ROLE_PERMISSIONS["engagement_lead"]

    def test_client_viewer_limited_permissions(self) -> None:
        """Client viewer should only have read permissions."""
        perms = ROLE_PERMISSIONS["client_viewer"]
        assert "engagement:read" in perms
        assert "pov:read" in perms
        assert "evidence:create" not in perms

    def test_process_analyst_can_create_evidence(self) -> None:
        """Process analyst should be able to create evidence."""
        perms = ROLE_PERMISSIONS["process_analyst"]
        assert "evidence:create" in perms
        assert "evidence:read" in perms

    def test_evidence_reviewer_can_validate(self) -> None:
        """Evidence reviewer should have validate permission."""
        perms = ROLE_PERMISSIONS["evidence_reviewer"]
        assert "evidence:validate" in perms
        assert "evidence:create" not in perms


# ---------------------------------------------------------------------------
# has_permission
# ---------------------------------------------------------------------------


class TestHasPermission:
    """Tests for the has_permission function."""

    def test_admin_has_any_permission(self) -> None:
        """Platform admin should have any permission via wildcard."""
        user = _make_user(UserRole.PLATFORM_ADMIN)
        assert has_permission(user, "engagement:create") is True
        assert has_permission(user, "evidence:delete") is True
        assert has_permission(user, "nonexistent:permission") is True

    def test_engagement_lead_has_allowed_permission(self) -> None:
        """Engagement lead should have their listed permissions."""
        user = _make_user(UserRole.ENGAGEMENT_LEAD)
        assert has_permission(user, "engagement:create") is True
        assert has_permission(user, "evidence:create") is True

    def test_engagement_lead_lacks_unlisted_permission(self) -> None:
        """Engagement lead should not have permissions not in their list."""
        user = _make_user(UserRole.ENGAGEMENT_LEAD)
        assert has_permission(user, "evidence:validate") is False

    def test_client_viewer_lacks_write_permissions(self) -> None:
        """Client viewer should not have write permissions."""
        user = _make_user(UserRole.CLIENT_VIEWER)
        assert has_permission(user, "evidence:create") is False
        assert has_permission(user, "engagement:update") is False

    def test_process_analyst_permissions(self) -> None:
        """Process analyst should have their defined set of permissions."""
        user = _make_user(UserRole.PROCESS_ANALYST)
        assert has_permission(user, "engagement:read") is True
        assert has_permission(user, "pov:generate") is True
        assert has_permission(user, "team:manage") is False


# ---------------------------------------------------------------------------
# has_role_level
# ---------------------------------------------------------------------------


class TestHasRoleLevel:
    """Tests for role hierarchy checking."""

    def test_admin_exceeds_all_roles(self) -> None:
        """Platform admin should meet any role requirement."""
        user = _make_user(UserRole.PLATFORM_ADMIN)
        assert has_role_level(user, UserRole.PLATFORM_ADMIN) is True
        assert has_role_level(user, UserRole.ENGAGEMENT_LEAD) is True
        assert has_role_level(user, UserRole.CLIENT_VIEWER) is True

    def test_client_viewer_only_meets_own_level(self) -> None:
        """Client viewer should only meet client_viewer level."""
        user = _make_user(UserRole.CLIENT_VIEWER)
        assert has_role_level(user, UserRole.CLIENT_VIEWER) is True
        assert has_role_level(user, UserRole.EVIDENCE_REVIEWER) is False
        assert has_role_level(user, UserRole.PLATFORM_ADMIN) is False

    def test_engagement_lead_meets_mid_levels(self) -> None:
        """Engagement lead should meet mid-level requirements."""
        user = _make_user(UserRole.ENGAGEMENT_LEAD)
        assert has_role_level(user, UserRole.ENGAGEMENT_LEAD) is True
        assert has_role_level(user, UserRole.PROCESS_ANALYST) is True
        assert has_role_level(user, UserRole.PLATFORM_ADMIN) is False

    def test_role_hierarchy_order(self) -> None:
        """ROLE_HIERARCHY should be ordered most to least privileged."""
        assert ROLE_HIERARCHY[0] == UserRole.PLATFORM_ADMIN
        assert ROLE_HIERARCHY[-1] == UserRole.CLIENT_VIEWER
