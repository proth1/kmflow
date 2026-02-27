"""Add data_processing_activities and retention_policies tables.

Revision ID: 068
Revises: 067
Create Date: 2026-02-27

Story #317: Data Classification and GDPR Compliance Framework — ROPA
tracking, per-engagement retention policies, and lawful basis documentation.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "068"
down_revision = "067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Lawful basis enum --
    lawful_basis_enum = sa.Enum(
        "consent", "contract", "legal_obligation",
        "vital_interests", "public_task", "legitimate_interests",
        name="lawfulbasis",
    )

    # -- Retention action enum --
    retention_action_enum = sa.Enum(
        "archive", "delete",
        name="retentionaction",
    )

    # -- Data processing activities (ROPA) --
    op.create_table(
        "data_processing_activities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("lawful_basis", lawful_basis_enum, nullable=False),
        sa.Column(
            "article_6_basis",
            sa.String(50),
            nullable=False,
            server_default="Art. 6(1)(f)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_data_processing_activities_engagement_id",
        "data_processing_activities",
        ["engagement_id"],
    )

    # -- Retention policies --
    op.create_table(
        "retention_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retention_days", sa.Integer, nullable=False, server_default="365"),
        sa.Column(
            "action",
            retention_action_enum,
            nullable=False,
            server_default="archive",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_retention_policies_engagement_id",
        "retention_policies",
        ["engagement_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_retention_policies_engagement_id", table_name="retention_policies")
    op.drop_table("retention_policies")

    sa.Enum(name="retentionaction").drop(op.get_bind(), checkfirst=True)

    op.drop_index(
        "ix_data_processing_activities_engagement_id",
        table_name="data_processing_activities",
    )
    op.drop_table("data_processing_activities")

    sa.Enum(name="lawfulbasis").drop(op.get_bind(), checkfirst=True)
