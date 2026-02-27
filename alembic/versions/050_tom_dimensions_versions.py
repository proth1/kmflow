"""Add tom_dimensions and tom_versions tables, add version column to target_operating_models.

Revision ID: 050
Revises: 049
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add version column to target_operating_models
    op.add_column(
        "target_operating_models",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    # Create tom_dimensions table
    op.create_table(
        "tom_dimensions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tom_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("target_operating_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dimension_type",
            sa.Enum(
                "process_architecture",
                "people_and_organization",
                "technology_and_data",
                "governance_structures",
                "performance_management",
                "risk_and_compliance",
                name="tomdimension",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("maturity_target", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("tom_id", "dimension_type", name="uq_tom_dimension_type"),
    )
    op.create_index("ix_tom_dimensions_tom_id", "tom_dimensions", ["tom_id"])

    # Create tom_versions table
    op.create_table(
        "tom_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tom_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("target_operating_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSON(), nullable=False),
        sa.Column("changed_by", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tom_id", "version_number", name="uq_tom_version_number"),
    )
    op.create_index("ix_tom_versions_tom_id", "tom_versions", ["tom_id"])


def downgrade() -> None:
    op.drop_index("ix_tom_versions_tom_id", table_name="tom_versions")
    op.drop_table("tom_versions")
    op.drop_index("ix_tom_dimensions_tom_id", table_name="tom_dimensions")
    op.drop_table("tom_dimensions")
    op.drop_column("target_operating_models", "version")
