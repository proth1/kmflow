"""Add policy_bundles and endpoint_consent_records tables.

Revision ID: 067
Revises: 066
Create Date: 2026-02-27

Story #382: Consent Architecture for Endpoint Capture — platform-level
consent model with OPT_IN/ORG_AUTHORIZED/HYBRID modes, policy bundle
versioning, and 7-year retention floor.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Policy bundles --
    op.create_table(
        "policy_bundles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column(
            "scope",
            sa.String(512),
            nullable=False,
            server_default="application-usage-monitoring",
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_policy_bundles_engagement_id",
        "policy_bundles",
        ["engagement_id"],
    )

    # -- Endpoint consent records --
    consent_type_enum = sa.Enum(
        "opt_in", "org_authorized", "hybrid",
        name="endpointconsenttype",
    )
    consent_status_enum = sa.Enum(
        "active", "withdrawn",
        name="consentstatus_endpoint",
    )

    op.create_table(
        "endpoint_consent_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "participant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("consent_type", consent_type_enum, nullable=False),
        sa.Column(
            "scope",
            sa.String(512),
            nullable=False,
            server_default="application-usage-monitoring",
        ),
        sa.Column(
            "policy_bundle_id",
            UUID(as_uuid=True),
            sa.ForeignKey("policy_bundles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            consent_status_enum,
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "recorded_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_endpoint_consent_records_participant_id",
        "endpoint_consent_records",
        ["participant_id"],
    )
    op.create_index(
        "ix_endpoint_consent_records_engagement_id",
        "endpoint_consent_records",
        ["engagement_id"],
    )
    op.create_index(
        "ix_endpoint_consent_records_status",
        "endpoint_consent_records",
        ["status"],
    )


    # Immutability enforcement: prevent UPDATE on core fields.
    # Only status and withdrawn_at may be modified (for withdrawal).
    op.execute("""
        CREATE OR REPLACE FUNCTION enforce_consent_record_immutability()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.participant_id IS DISTINCT FROM NEW.participant_id
                OR OLD.engagement_id IS DISTINCT FROM NEW.engagement_id
                OR OLD.consent_type IS DISTINCT FROM NEW.consent_type
                OR OLD.policy_bundle_id IS DISTINCT FROM NEW.policy_bundle_id
                OR OLD.recorded_by IS DISTINCT FROM NEW.recorded_by
                OR OLD.recorded_at IS DISTINCT FROM NEW.recorded_at
                OR OLD.retention_expires_at IS DISTINCT FROM NEW.retention_expires_at
            THEN
                RAISE EXCEPTION 'endpoint_consent_records: core fields are immutable after creation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_consent_records_immutability
        BEFORE UPDATE ON endpoint_consent_records
        FOR EACH ROW EXECUTE FUNCTION enforce_consent_record_immutability();
    """)

    # Prevent DELETE on consent records (7-year retention floor).
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_consent_record_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'endpoint_consent_records: DELETE is prohibited (7-year retention floor)';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_consent_records_no_delete
        BEFORE DELETE ON endpoint_consent_records
        FOR EACH ROW EXECUTE FUNCTION prevent_consent_record_delete();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_consent_records_no_delete ON endpoint_consent_records;")
    op.execute("DROP TRIGGER IF EXISTS trg_consent_records_immutability ON endpoint_consent_records;")
    op.execute("DROP FUNCTION IF EXISTS prevent_consent_record_delete();")
    op.execute("DROP FUNCTION IF EXISTS enforce_consent_record_immutability();")

    op.drop_index(
        "ix_endpoint_consent_records_status",
        table_name="endpoint_consent_records",
    )
    op.drop_index(
        "ix_endpoint_consent_records_engagement_id",
        table_name="endpoint_consent_records",
    )
    op.drop_index(
        "ix_endpoint_consent_records_participant_id",
        table_name="endpoint_consent_records",
    )
    op.drop_table("endpoint_consent_records")

    # Drop enum types
    sa.Enum(name="consentstatus_endpoint").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="endpointconsenttype").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_policy_bundles_engagement_id", table_name="policy_bundles")
    op.drop_table("policy_bundles")
