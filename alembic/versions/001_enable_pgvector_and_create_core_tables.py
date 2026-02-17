"""Enable pgvector extension and create core tables.

Revision ID: 001
Revises: None
Create Date: 2026-02-17
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── engagements ──────────────────────────────────────────
    op.create_table(
        "engagements",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("client", sa.String(255), nullable=False),
        sa.Column("business_area", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "in_review", "completed", "archived", name="engagementstatus"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── evidence_items ───────────────────────────────────────
    op.create_table(
        "evidence_items",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("engagement_id", sa.UUID(), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
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
            ),
            nullable=False,
        ),
        sa.Column("format", sa.String(50), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("completeness_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("reliability_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("freshness_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("consistency_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "validation_status",
            sa.Enum("pending", "validated", "active", "expired", "archived", name="validationstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index(
        "ix_evidence_engagement_category",
        "evidence_items",
        ["engagement_id", "category"],
    )

    # ── evidence_fragments ───────────────────────────────────
    op.create_table(
        "evidence_fragments",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "evidence_id",
            sa.UUID(),
            sa.ForeignKey("evidence_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "fragment_type",
            sa.Enum(
                "text",
                "table",
                "image",
                "entity",
                "relationship",
                "process_element",
                name="fragmenttype",
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create HNSW index for vector similarity search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evidence_fragments_embedding "
        "ON evidence_fragments USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_table("evidence_fragments")
    op.drop_table("evidence_items")
    op.drop_table("engagements")

    op.execute("DROP TYPE IF EXISTS fragmenttype")
    op.execute("DROP TYPE IF EXISTS validationstatus")
    op.execute("DROP TYPE IF EXISTS evidencecategory")
    op.execute("DROP TYPE IF EXISTS engagementstatus")

    op.execute("DROP EXTENSION IF EXISTS vector")
