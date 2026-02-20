"""Add GDPR erasure fields to users and create user_consents table.

Revision ID: 023
Revises: 022
Create Date: 2026-02-20

Changes:
- users: add erasure_requested_at (TIMESTAMPTZ, nullable)
- users: add erasure_scheduled_at (TIMESTAMPTZ, nullable)
- create user_consents table
- add index on user_consents.user_id
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # -- users: GDPR erasure timestamp columns -----------------------------------
    op.add_column(
        "users",
        sa.Column(
            "erasure_requested_at",
            sa.DateTime(timezone=True),
            nullable=True,
            default=None,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "erasure_scheduled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            default=None,
        ),
    )

    # -- user_consents table -----------------------------------------------------
    op.create_table(
        "user_consents",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("consent_type", sa.String(100), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
    )

    # -- index on user_consents.user_id ------------------------------------------
    op.create_index(
        "ix_user_consents_user_id",
        "user_consents",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_consents_user_id", table_name="user_consents")
    op.drop_table("user_consents")
    op.drop_column("users", "erasure_scheduled_at")
    op.drop_column("users", "erasure_requested_at")
