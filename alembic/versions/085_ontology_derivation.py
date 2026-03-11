"""Ontology derivation tables (KMFLOW-6).

Revision ID: 085
Revises: 084
Create Date: 2026-03-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "085"
down_revision = "084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- ontology_versions --
    op.create_table(
        "ontology_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status",
            sa.Enum("deriving", "derived", "validated", "exported", name="ontologystatus"),
            nullable=False,
            server_default="deriving",
        ),
        sa.Column("completeness_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("class_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("property_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("axiom_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("derived_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ontology_versions_engagement_id", "ontology_versions", ["engagement_id"])
    op.create_index("ix_ontology_versions_engagement_status", "ontology_versions", ["engagement_id", "status"])

    # RLS
    op.execute("ALTER TABLE ontology_versions ENABLE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY ontology_versions_engagement_isolation ON ontology_versions
           USING (engagement_id = current_setting('app.current_engagement_id')::uuid)"""
    )

    # -- ontology_classes --
    op.create_table(
        "ontology_classes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ontology_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ontology_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "parent_class_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ontology_classes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_seed_terms", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("instance_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ontology_classes_ontology_id", "ontology_classes", ["ontology_id"])

    # -- ontology_properties --
    op.create_table(
        "ontology_properties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ontology_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ontology_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("source_edge_type", sa.String(100), nullable=False),
        sa.Column(
            "domain_class_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ontology_classes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "range_class_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ontology_classes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ontology_properties_ontology_id", "ontology_properties", ["ontology_id"])

    # -- ontology_axioms --
    op.create_table(
        "ontology_axioms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ontology_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ontology_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expression", sa.Text(), nullable=False),
        sa.Column("axiom_type", sa.String(100), nullable=False),
        sa.Column("source_pattern", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ontology_axioms_ontology_id", "ontology_axioms", ["ontology_id"])


def downgrade() -> None:
    op.drop_table("ontology_axioms")
    op.drop_table("ontology_properties")
    op.drop_table("ontology_classes")
    op.drop_table("ontology_versions")
    op.execute("DROP TYPE IF EXISTS ontologystatus")
