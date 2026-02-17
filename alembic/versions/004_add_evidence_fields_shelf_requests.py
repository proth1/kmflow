"""Add file storage fields to evidence_items, create shelf data request tables.

Revision ID: 004
Revises: 003
Create Date: 2026-02-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Add new columns to evidence_items --
    op.add_column("evidence_items", sa.Column("file_path", sa.String(1024), nullable=True))
    op.add_column("evidence_items", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("evidence_items", sa.Column("mime_type", sa.String(255), nullable=True))
    op.add_column("evidence_items", sa.Column("metadata_json", sa.JSON(), nullable=True))
    op.add_column("evidence_items", sa.Column("source_date", sa.Date(), nullable=True))
    op.add_column(
        "evidence_items",
        sa.Column(
            "duplicate_of_id",
            sa.UUID(),
            sa.ForeignKey("evidence_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # -- Add new audit actions to enum type --
    # PostgreSQL requires explicit enum type alteration
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'evidence_uploaded'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'evidence_validated'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'shelf_request_created'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'shelf_request_updated'")

    # -- Create shelf_data_requests table --
    op.create_table(
        "shelf_data_requests",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "engagement_id",
            sa.UUID(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "sent", "in_progress", "completed", "overdue", name="shelfrequeststatus"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_shelf_requests_engagement_id", "shelf_data_requests", ["engagement_id"])

    # -- Create shelf_data_request_items table --
    op.create_table(
        "shelf_data_request_items",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "request_id",
            sa.UUID(),
            sa.ForeignKey("shelf_data_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.Enum(
                "documents",
                "images",
                "audio",
                "video",
                "structured_data",
                "saas_exports",
                "km4work",
                "bpm_process_models",
                "regulatory_policy",
                "controls_evidence",
                "domain_communications",
                "job_aids_edge_cases",
                name="evidencecategory",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("item_name", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "priority",
            sa.Enum("high", "medium", "low", name="shelfrequestItempriority"),
            nullable=False,
            server_default="medium",
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "received", "overdue", name="shelfrequestitemstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "matched_evidence_id",
            sa.UUID(),
            sa.ForeignKey("evidence_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_shelf_request_items_request_id", "shelf_data_request_items", ["request_id"])


def downgrade() -> None:
    op.drop_table("shelf_data_request_items")
    op.execute("DROP TYPE IF EXISTS shelfrequestItempriority")
    op.execute("DROP TYPE IF EXISTS shelfrequestitemstatus")

    op.drop_table("shelf_data_requests")
    op.execute("DROP TYPE IF EXISTS shelfrequeststatus")

    op.drop_column("evidence_items", "duplicate_of_id")
    op.drop_column("evidence_items", "source_date")
    op.drop_column("evidence_items", "metadata_json")
    op.drop_column("evidence_items", "mime_type")
    op.drop_column("evidence_items", "size_bytes")
    op.drop_column("evidence_items", "file_path")
