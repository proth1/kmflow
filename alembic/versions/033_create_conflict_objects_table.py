"""Create conflict_objects table.

Adds the ConflictObject table for cross-source inconsistency tracking
per PRD v2.1 Section 6.10.5 (Cross-Source Consistency Checks).

Revision ID: 033
Revises: 032
Create Date: 2026-02-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "033"
down_revision: str | None = "032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MISMATCH_TYPE = sa.Enum(
    "sequence_mismatch",
    "role_mismatch",
    "rule_mismatch",
    "existence_mismatch",
    "io_mismatch",
    "control_gap",
    name="mismatchtype",
)
_RESOLUTION_TYPE = sa.Enum(
    "genuine_disagreement",
    "naming_variant",
    "temporal_shift",
    name="resolutiontype",
)
_RESOLUTION_STATUS = sa.Enum(
    "unresolved",
    "resolved",
    "escalated",
    name="resolutionstatus",
)


def upgrade() -> None:
    _MISMATCH_TYPE.create(op.get_bind(), checkfirst=True)
    _RESOLUTION_TYPE.create(op.get_bind(), checkfirst=True)
    _RESOLUTION_STATUS.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "conflict_objects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id", UUID(as_uuid=True), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("mismatch_type", _MISMATCH_TYPE, nullable=False),
        sa.Column("resolution_type", _RESOLUTION_TYPE, nullable=True),
        sa.Column("resolution_status", _RESOLUTION_STATUS, nullable=False, server_default="unresolved"),
        sa.Column(
            "source_a_id", UUID(as_uuid=True), sa.ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "source_b_id", UUID(as_uuid=True), sa.ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("severity", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("escalation_flag", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_conflict_objects_engagement_status", "conflict_objects", ["engagement_id", "resolution_status"])
    op.create_index("ix_conflict_objects_engagement_id", "conflict_objects", ["engagement_id"])
    op.create_index("ix_conflict_objects_source_a_id", "conflict_objects", ["source_a_id"])
    op.create_index("ix_conflict_objects_source_b_id", "conflict_objects", ["source_b_id"])


def downgrade() -> None:
    op.drop_table("conflict_objects")
    _RESOLUTION_STATUS.drop(op.get_bind(), checkfirst=True)
    _RESOLUTION_TYPE.drop(op.get_bind(), checkfirst=True)
    _MISMATCH_TYPE.drop(op.get_bind(), checkfirst=True)
