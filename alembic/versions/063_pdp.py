"""Add Policy Decision Point (PDP) tables.

Revision ID: 063
Revises: 062
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pdp_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("conditions_json", JSON, nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("obligations_json", JSON, nullable=True),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("priority", sa.Integer, nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pdp_policies_active", "pdp_policies", ["is_active"])

    op.create_table(
        "pdp_audit_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id", UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=False),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("obligations_json", JSON, nullable=True),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("policy_id", UUID(as_uuid=True), nullable=True),
        sa.Column("request_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pdp_audit_actor", "pdp_audit_entries", ["actor"])
    op.create_index("ix_pdp_audit_engagement", "pdp_audit_entries", ["engagement_id"])


def downgrade() -> None:
    op.drop_index("ix_pdp_audit_engagement", table_name="pdp_audit_entries")
    op.drop_index("ix_pdp_audit_actor", table_name="pdp_audit_entries")
    op.drop_table("pdp_audit_entries")
    op.drop_index("ix_pdp_policies_active", table_name="pdp_policies")
    op.drop_table("pdp_policies")
