"""Create semantic_relationships table with bitemporal validity.

Adds the SemanticRelationship table for dual-store relationship tracking
with bitemporal properties per PRD v2.1 Section 6.2.

Revision ID: 035
Revises: 034
Create Date: 2026-02-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "035"
down_revision: str | None = "034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "semantic_relationships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_node_id", sa.String(500), nullable=False),
        sa.Column("target_node_id", sa.String(500), nullable=False),
        sa.Column("edge_type", sa.String(100), nullable=False),
        # Bitemporal validity properties
        sa.Column(
            "asserted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("retracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "superseded_by",
            UUID(as_uuid=True),
            sa.ForeignKey("semantic_relationships.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_semantic_relationships_engagement_id", "semantic_relationships", ["engagement_id"])
    op.create_index("ix_semantic_relationships_source_node_id", "semantic_relationships", ["source_node_id"])
    op.create_index("ix_semantic_relationships_target_node_id", "semantic_relationships", ["target_node_id"])
    op.create_index("ix_semantic_relationships_retracted_at", "semantic_relationships", ["retracted_at"])
    op.create_index("ix_semantic_relationships_edge_type", "semantic_relationships", ["edge_type"])
    op.create_index("ix_semantic_relationships_superseded_by", "semantic_relationships", ["superseded_by"])


def downgrade() -> None:
    op.drop_table("semantic_relationships")
