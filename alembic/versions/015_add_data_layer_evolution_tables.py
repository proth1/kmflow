"""Add data layer evolution tables: evidence_lineage, data_catalog_entries.

Also adds source_system, delta_path, lineage_id columns to evidence_items.

Revision ID: 015
Revises: 014
Create Date: 2026-02-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum values
DATA_LAYER_VALUES = ("bronze", "silver", "gold")
DATA_CLASSIFICATION_VALUES = ("public", "internal", "confidential", "restricted")

data_layer_enum = sa.Enum(*DATA_LAYER_VALUES, name="datalayer")
data_classification_enum = sa.Enum(*DATA_CLASSIFICATION_VALUES, name="dataclassification")


def upgrade() -> None:
    # -- Create enums --
    data_layer_enum.create(op.get_bind(), checkfirst=True)
    data_classification_enum.create(op.get_bind(), checkfirst=True)

    # -- Add columns to evidence_items --
    op.add_column("evidence_items", sa.Column("source_system", sa.String(255), nullable=True))
    op.add_column("evidence_items", sa.Column("delta_path", sa.String(1024), nullable=True))
    op.add_column("evidence_items", sa.Column("lineage_id", sa.UUID(), nullable=True))

    # -- evidence_lineage --
    op.create_table(
        "evidence_lineage",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "evidence_item_id",
            sa.UUID(),
            sa.ForeignKey("evidence_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_system", sa.String(255), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("source_identifier", sa.String(512), nullable=True),
        sa.Column("transformation_chain", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("version_hash", sa.String(64), nullable=True),
        sa.Column(
            "parent_version_id",
            sa.UUID(),
            sa.ForeignKey("evidence_lineage.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("refresh_schedule", sa.String(100), nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_evidence_lineage_evidence_item_id", "evidence_lineage", ["evidence_item_id"])
    op.create_index("ix_evidence_lineage_source_system", "evidence_lineage", ["source_system"])

    # -- data_catalog_entries --
    op.create_table(
        "data_catalog_entries",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "engagement_id",
            sa.UUID(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("dataset_name", sa.String(512), nullable=False),
        sa.Column("dataset_type", sa.String(100), nullable=False),
        sa.Column("layer", data_layer_enum, nullable=False),
        sa.Column("schema_definition", sa.JSON(), nullable=True),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("classification", data_classification_enum, nullable=False, server_default="internal"),
        sa.Column("quality_sla", sa.JSON(), nullable=True),
        sa.Column("retention_days", sa.BigInteger(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("row_count", sa.BigInteger(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("delta_table_path", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_data_catalog_entries_layer", "data_catalog_entries", ["layer"])
    op.create_index("ix_data_catalog_entries_engagement_id", "data_catalog_entries", ["engagement_id"])


def downgrade() -> None:
    op.drop_table("data_catalog_entries")
    op.drop_table("evidence_lineage")
    op.drop_column("evidence_items", "lineage_id")
    op.drop_column("evidence_items", "delta_path")
    op.drop_column("evidence_items", "source_system")
    data_classification_enum.drop(op.get_bind(), checkfirst=True)
    data_layer_enum.drop(op.get_bind(), checkfirst=True)
