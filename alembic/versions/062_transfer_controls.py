"""Add cross-border data transfer control tables.

Revision ID: 061
Revises: 060
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transfer_impact_assessments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id", UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("connector_id", sa.String(255), nullable=False),
        sa.Column("destination_jurisdiction", sa.String(10), nullable=False),
        sa.Column("assessor", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tia_engagement_id", "transfer_impact_assessments", ["engagement_id"])
    op.create_index("ix_tia_connector_id", "transfer_impact_assessments", ["connector_id"])

    op.create_table(
        "standard_contractual_clauses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id", UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("connector_id", sa.String(255), nullable=False),
        sa.Column("scc_version", sa.String(50), nullable=False),
        sa.Column("reference_id", sa.String(255), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scc_engagement_id", "standard_contractual_clauses", ["engagement_id"])
    op.create_index("ix_scc_connector_id", "standard_contractual_clauses", ["connector_id"])

    op.create_table(
        "data_transfer_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id", UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("connector_id", sa.String(255), nullable=False),
        sa.Column("destination_jurisdiction", sa.String(10), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("scc_reference_id", sa.String(255), nullable=True),
        sa.Column("tia_id", UUID(as_uuid=True), nullable=True),
        sa.Column("details_json", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_dtl_engagement_id", "data_transfer_log", ["engagement_id"])
    op.create_index("ix_dtl_connector_id", "data_transfer_log", ["connector_id"])


def downgrade() -> None:
    op.drop_index("ix_dtl_connector_id", table_name="data_transfer_log")
    op.drop_index("ix_dtl_engagement_id", table_name="data_transfer_log")
    op.drop_table("data_transfer_log")
    op.drop_index("ix_scc_connector_id", table_name="standard_contractual_clauses")
    op.drop_index("ix_scc_engagement_id", table_name="standard_contractual_clauses")
    op.drop_table("standard_contractual_clauses")
    op.drop_index("ix_tia_connector_id", table_name="transfer_impact_assessments")
    op.drop_index("ix_tia_engagement_id", table_name="transfer_impact_assessments")
    op.drop_table("transfer_impact_assessments")
