"""091: Add data_processing_agreements table for GDPR Article 28 DPA tracking.

Creates the DPA table with engagement FK, status lifecycle enum, and indexes.
Adds DPA audit action enum values. Applies RLS for engagement-scoped isolation.

Revision ID: 091
Revises: 090
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.core.rls import apply_engagement_rls, remove_engagement_rls

revision = "091"
down_revision = "090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create DpaStatus enum type
    dpa_status_enum = sa.Enum("draft", "active", "superseded", "expired", name="dpastatus")
    dpa_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "data_processing_agreements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "engagement_id", UUID(as_uuid=True), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("reference_number", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("status", dpa_status_enum, nullable=False, server_default="draft"),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("expiry_date", sa.Date, nullable=True),
        sa.Column("controller_name", sa.String(255), nullable=False),
        sa.Column("processor_name", sa.String(255), nullable=False),
        sa.Column("data_categories", JSONB, nullable=False),
        sa.Column("sub_processors", JSONB, nullable=True),
        sa.Column("retention_days_override", sa.Integer, nullable=True),
        sa.Column(
            "lawful_basis",
            sa.Enum(
                "consent",
                "contract",
                "legal_obligation",
                "vital_interests",
                "public_task",
                "legitimate_interests",
                name="lawfulbasis",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_data_processing_agreements_engagement_id", "data_processing_agreements", ["engagement_id"])
    op.create_index(
        "ix_data_processing_agreements_engagement_status",
        "data_processing_agreements",
        ["engagement_id", "status"],
    )

    # Add new audit action enum values
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'dpa_created'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'dpa_updated'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'dpa_activated'")

    # Apply RLS
    for stmt in apply_engagement_rls("data_processing_agreements"):
        op.execute(stmt)


def downgrade() -> None:
    # Remove RLS
    for stmt in remove_engagement_rls("data_processing_agreements"):
        op.execute(stmt)

    op.drop_index("ix_data_processing_agreements_engagement_status")
    op.drop_index("ix_data_processing_agreements_engagement_id")
    op.drop_table("data_processing_agreements")

    # Note: PostgreSQL does not support removing enum values, so dpastatus
    # and the audit action values are left in place on downgrade.
