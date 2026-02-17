"""Create regulatory/policy/control tables.

Tables: policies, controls, regulations.

Revision ID: 007
Revises: 006
Create Date: 2026-02-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Create enum types --
    op.execute(
        "CREATE TYPE policytype AS ENUM "
        "('organizational', 'regulatory', 'operational', 'security')"
    )
    op.execute(
        "CREATE TYPE controleffectiveness AS ENUM "
        "('highly_effective', 'effective', 'moderately_effective', 'ineffective')"
    )
    op.execute(
        "CREATE TYPE compliancelevel AS ENUM "
        "('fully_compliant', 'partially_compliant', 'non_compliant', 'not_assessed')"
    )

    # -- Create policies table --
    op.create_table(
        "policies",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "engagement_id",
            sa.UUID(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column(
            "policy_type",
            sa.Enum(
                "organizational", "regulatory", "operational", "security",
                name="policytype", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "source_evidence_id",
            sa.UUID(),
            sa.ForeignKey("evidence_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("clauses", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_policies_engagement_id", "policies", ["engagement_id"])

    # -- Create controls table --
    op.create_table(
        "controls",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "engagement_id",
            sa.UUID(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "effectiveness",
            sa.Enum(
                "highly_effective", "effective", "moderately_effective", "ineffective",
                name="controleffectiveness", create_type=False,
            ),
            nullable=False,
            server_default="effective",
        ),
        sa.Column(
            "effectiveness_score", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column("linked_policy_ids", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_controls_engagement_id", "controls", ["engagement_id"])

    # -- Create regulations table --
    op.create_table(
        "regulations",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "engagement_id",
            sa.UUID(),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("framework", sa.String(255), nullable=True),
        sa.Column("jurisdiction", sa.String(255), nullable=True),
        sa.Column("obligations", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_regulations_engagement_id", "regulations", ["engagement_id"])


def downgrade() -> None:
    op.drop_table("regulations")
    op.drop_table("controls")
    op.drop_table("policies")

    op.execute("DROP TYPE IF EXISTS compliancelevel")
    op.execute("DROP TYPE IF EXISTS controleffectiveness")
    op.execute("DROP TYPE IF EXISTS policytype")
