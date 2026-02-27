"""Add compliance_assessments table for per-activity compliance state tracking.

Revision ID: 053
Revises: 052
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compliance_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("process_elements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "engagement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.Enum(
                "fully_compliant",
                "partially_compliant",
                "non_compliant",
                "not_assessed",
                name="compliancelevel",
                create_type=False,
            ),
            nullable=False,
            server_default="not_assessed",
        ),
        sa.Column("control_coverage_percentage", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
        sa.Column("total_required_controls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("controls_with_evidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gaps", postgresql.JSON(), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("assessed_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_compliance_assessments_activity_id", "compliance_assessments", ["activity_id"])
    op.create_index("ix_compliance_assessments_engagement_id", "compliance_assessments", ["engagement_id"])
    op.create_index("ix_compliance_assessments_assessed_at", "compliance_assessments", ["assessed_at"])


def downgrade() -> None:
    op.drop_index("ix_compliance_assessments_assessed_at", table_name="compliance_assessments")
    op.drop_index("ix_compliance_assessments_engagement_id", table_name="compliance_assessments")
    op.drop_index("ix_compliance_assessments_activity_id", table_name="compliance_assessments")
    op.drop_table("compliance_assessments")
