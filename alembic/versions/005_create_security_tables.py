"""Create users and engagement_members tables for security and authentication.

Revision ID: 005
Revises: 004
Create Date: 2026-02-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Create UserRole enum type --
    op.execute(
        "CREATE TYPE userrole AS ENUM "
        "('platform_admin', 'engagement_lead', 'process_analyst', "
        "'evidence_reviewer', 'client_viewer')"
    )

    # -- Add new audit action values --
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'login'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'logout'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'permission_denied'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'data_access'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'pov_generated'")

    # -- Create users table --
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "platform_admin",
                "engagement_lead",
                "process_analyst",
                "evidence_reviewer",
                "client_viewer",
                name="userrole",
                create_type=False,
            ),
            nullable=False,
            server_default="process_analyst",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("external_id", sa.String(255), unique=True, nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_external_id", "users", ["external_id"])

    # -- Create engagement_members table --
    op.create_table(
        "engagement_members",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "engagement_id",
            sa.UUID(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role_in_engagement", sa.String(100), nullable=False, server_default="member"),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("engagement_id", "user_id", name="uq_engagement_user"),
    )
    op.create_index("ix_engagement_members_engagement_id", "engagement_members", ["engagement_id"])
    op.create_index("ix_engagement_members_user_id", "engagement_members", ["user_id"])


def downgrade() -> None:
    op.drop_table("engagement_members")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS userrole")
