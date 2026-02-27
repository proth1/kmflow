"""Add Policy Decision Point (PDP) tables.

Revision ID: 063
Revises: 062
Create Date: 2026-02-27
"""

from __future__ import annotations

import uuid

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


    # Seed default policies so the system does not start fully-open
    policies_table = sa.table(
        "pdp_policies",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("conditions_json", JSON),
        sa.column("decision", sa.String),
        sa.column("obligations_json", JSON),
        sa.column("reason", sa.String),
        sa.column("priority", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        policies_table,
        [
            {
                "id": str(uuid.uuid4()),
                "name": "deny_restricted_below_lead",
                "description": "Deny restricted data access for roles below engagement_lead",
                "conditions_json": {"classification": "restricted", "max_role": "process_analyst"},
                "decision": "deny",
                "obligations_json": None,
                "reason": "insufficient_clearance",
                "priority": 10,
                "is_active": True,
            },
            {
                "id": str(uuid.uuid4()),
                "name": "watermark_confidential_export",
                "description": "Require watermark on confidential data exports",
                "conditions_json": {"classification": "confidential", "operation": "export"},
                "decision": "permit",
                "obligations_json": [{"type": "apply_watermark", "params": {"visible": True}}],
                "reason": "export_permitted_with_watermark",
                "priority": 20,
                "is_active": True,
            },
            {
                "id": str(uuid.uuid4()),
                "name": "enhanced_audit_restricted",
                "description": "Require enhanced audit for restricted data access by authorized roles",
                "conditions_json": {"classification": "restricted", "min_role": "engagement_lead"},
                "decision": "permit",
                "obligations_json": [{"type": "log_enhanced_audit", "params": {}}],
                "reason": "access_permitted_with_enhanced_audit",
                "priority": 50,
                "is_active": True,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_pdp_audit_engagement", table_name="pdp_audit_entries")
    op.drop_index("ix_pdp_audit_actor", table_name="pdp_audit_entries")
    op.drop_table("pdp_audit_entries")
    op.drop_index("ix_pdp_policies_active", table_name="pdp_policies")
    op.drop_table("pdp_policies")
