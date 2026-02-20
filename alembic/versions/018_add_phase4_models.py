"""Add Phase 4 financial assumptions and alternative suggestions.

Creates financial_assumptions, alternative_suggestions tables
and supporting enums.

Revision ID: 018
Revises: 017
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enums
    assumption_type_enum = sa.Enum(
        "cost_per_role",
        "technology_cost",
        "volume_forecast",
        "implementation_cost",
        name="financialassumptiontype",
    )
    assumption_type_enum.create(op.get_bind(), checkfirst=True)

    disposition_enum = sa.Enum(
        "pending",
        "accepted",
        "modified",
        "rejected",
        name="suggestiondisposition",
    )
    disposition_enum.create(op.get_bind(), checkfirst=True)

    # financial_assumptions table
    op.create_table(
        "financial_assumptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "engagement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("assumption_type", assumption_type_enum, nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column(
            "source_evidence_id",
            UUID(as_uuid=True),
            sa.ForeignKey("evidence_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_financial_assumptions_engagement_id",
        "financial_assumptions",
        ["engagement_id"],
    )

    # alternative_suggestions table
    op.create_table(
        "alternative_suggestions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scenario_id",
            UUID(as_uuid=True),
            sa.ForeignKey("simulation_scenarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("suggestion_text", sa.Text, nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("governance_flags", sa.dialects.postgresql.JSON, nullable=True),
        sa.Column("evidence_gaps", sa.dialects.postgresql.JSON, nullable=True),
        sa.Column(
            "disposition",
            disposition_enum,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("disposition_notes", sa.Text, nullable=True),
        sa.Column("llm_prompt", sa.Text, nullable=False),
        sa.Column("llm_response", sa.Text, nullable=False),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_alternative_suggestions_scenario_id",
        "alternative_suggestions",
        ["scenario_id"],
    )

    # Extend auditaction enum
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'suggestion_created'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'suggestion_accepted'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'suggestion_rejected'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'financial_assumption_created'")


def downgrade() -> None:
    op.drop_index("ix_alternative_suggestions_scenario_id")
    op.drop_table("alternative_suggestions")
    op.drop_index("ix_financial_assumptions_engagement_id")
    op.drop_table("financial_assumptions")
    sa.Enum(name="suggestiondisposition").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="financialassumptiontype").drop(op.get_bind(), checkfirst=True)
