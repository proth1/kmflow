"""Add policy_bundles and policy_obligations tables for ABAC support.

Revision ID: 083
Revises: 082
Create Date: 2026-02-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "083"
down_revision = "082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pdp_policy_bundles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pdp_policy_bundles_active", "pdp_policy_bundles", ["is_active"])
    op.create_index("ix_pdp_policy_bundles_version", "pdp_policy_bundles", ["version"])

    op.create_table(
        "policy_obligations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "policy_id",
            UUID(as_uuid=True),
            sa.ForeignKey("pdp_policies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("obligation_type", sa.String(50), nullable=False),
        sa.Column("parameters", JSON, nullable=True),
        sa.Column("enforcement_point", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_policy_obligations_policy_id", "policy_obligations", ["policy_id"])
    op.create_index("ix_policy_obligations_type", "policy_obligations", ["obligation_type"])


def downgrade() -> None:
    op.drop_index("ix_policy_obligations_type", table_name="policy_obligations")
    op.drop_index("ix_policy_obligations_policy_id", table_name="policy_obligations")
    op.drop_table("policy_obligations")

    op.drop_index("ix_pdp_policy_bundles_version", table_name="pdp_policy_bundles")
    op.drop_index("ix_pdp_policy_bundles_active", table_name="pdp_policy_bundles")
    op.drop_table("pdp_policy_bundles")
