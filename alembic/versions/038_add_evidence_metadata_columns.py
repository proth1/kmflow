"""Add extracted_metadata JSONB and detected_language columns to evidence_items.

Supports automated metadata extraction during evidence ingestion (Story #304).

Revision ID: 038
Revises: 037
Create Date: 2026-02-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "038"
down_revision: str | None = "037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence_items", sa.Column("extracted_metadata", sa.JSON(), nullable=True))
    op.add_column("evidence_items", sa.Column("detected_language", sa.String(10), nullable=True))
    op.create_index("ix_evidence_items_detected_language", "evidence_items", ["detected_language"])


def downgrade() -> None:
    op.drop_index("ix_evidence_items_detected_language", table_name="evidence_items")
    op.drop_column("evidence_items", "detected_language")
    op.drop_column("evidence_items", "extracted_metadata")
