"""Create survey_claims and epistemic_frames tables.

Adds tables for structured knowledge elicitation per PRD v2.1
Section 6.2 (Epistemic Frame Properties) and Section 6.10.2
(Structured Survey Bot).

Revision ID: 032
Revises: 031
Create Date: 2026-02-27
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CERTAINTY_TIER = sa.Enum("known", "suspected", "unknown", "contradicted", name="certaintytier")
_PROBE_TYPE = sa.Enum(
    "existence", "sequence", "dependency", "input_output",
    "governance", "performer", "exception", "uncertainty",
    name="probetype",
)
_FRAME_KIND = sa.Enum(
    "procedural", "regulatory", "experiential",
    "telemetric", "elicited", "behavioral",
    name="framekind",
)


def upgrade() -> None:
    _CERTAINTY_TIER.create(op.get_bind(), checkfirst=True)
    _PROBE_TYPE.create(op.get_bind(), checkfirst=True)
    _FRAME_KIND.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "survey_claims",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("engagement_id", UUID(as_uuid=True), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("probe_type", _PROBE_TYPE, nullable=False),
        sa.Column("respondent_role", sa.String(255), nullable=False),
        sa.Column("claim_text", sa.Text, nullable=False),
        sa.Column("certainty_tier", _CERTAINTY_TIER, nullable=False),
        sa.Column("proof_expectation", sa.Text, nullable=True),
        sa.Column("related_seed_terms", JSON, nullable=True),
        sa.Column("metadata_json", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_survey_claims_engagement_id", "survey_claims", ["engagement_id"])
    op.create_index("ix_survey_claims_session_id", "survey_claims", ["session_id"])

    op.create_table(
        "epistemic_frames",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", UUID(as_uuid=True), sa.ForeignKey("survey_claims.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("engagement_id", UUID(as_uuid=True), sa.ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("frame_kind", _FRAME_KIND, nullable=False),
        sa.Column("authority_scope", sa.String(255), nullable=False),
        sa.Column("access_policy", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_epistemic_frames_claim_id", "epistemic_frames", ["claim_id"])
    op.create_index("ix_epistemic_frames_engagement_id", "epistemic_frames", ["engagement_id"])


def downgrade() -> None:
    op.drop_table("epistemic_frames")
    op.drop_table("survey_claims")
    _FRAME_KIND.drop(op.get_bind(), checkfirst=True)
    _PROBE_TYPE.drop(op.get_bind(), checkfirst=True)
    _CERTAINTY_TIER.drop(op.get_bind(), checkfirst=True)
