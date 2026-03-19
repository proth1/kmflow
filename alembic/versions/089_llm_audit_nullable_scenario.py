"""089: Make llm_audit_logs.scenario_id nullable for non-simulation LLM calls.

Allows LLMAuditLog to record copilot and TOM rationale generator calls
that do not operate within a simulation scenario context.

Revision ID: 089
Revises: 088
"""

from alembic import op

revision = "089"
down_revision = "088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("llm_audit_logs", "scenario_id", nullable=True)


def downgrade() -> None:
    # Re-adding the NOT NULL constraint requires no existing NULLs in the column.
    # Delete any rows without a scenario_id before reversing.
    op.execute("DELETE FROM llm_audit_logs WHERE scenario_id IS NULL")
    op.alter_column("llm_audit_logs", "scenario_id", nullable=False)
