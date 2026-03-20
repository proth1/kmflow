"""Row-Level Security (RLS) helpers for engagement-scoped data isolation.

Provides utilities for:
- Setting the current engagement context on a database session
- Applying RLS policies to engagement-scoped tables via Alembic
- Admin bypass mechanism for platform administrators

RLS Policy Pattern:
    USING (engagement_id = current_setting('app.current_engagement_id')::uuid)

Session Variable:
    SET LOCAL app.current_engagement_id = '<uuid>'
    (SET LOCAL is transaction-scoped, automatically reset on commit/rollback)
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Session variable name for engagement context
RLS_SESSION_VAR = "app.current_engagement_id"

# Regex for valid PostgreSQL table names (lowercase, underscores, digits)
_TABLE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

# Tables that have engagement_id and should receive RLS policies.
# Ordered alphabetically for consistency. Table names must match
# the __tablename__ attribute of their SQLAlchemy model exactly.
#
# Excluded from RLS (nullable engagement_id, special handling needed):
# - http_audit_events: string engagement_id (no FK), nullable
# - engagement_members: junction table, needs its own access pattern
# - alternative_suggestions: nullable engagement_id
# - pattern_library_entries: uses source_engagement_id (different column)
ENGAGEMENT_SCOPED_TABLES: list[str] = [
    "annotations",
    "assessment_matrix_entries",
    "audit_logs",
    "canonical_activity_events",
    "case_link_edges",
    "compliance_assessments",
    "conflict_objects",
    "conformance_results",
    "control_effectiveness_scores",
    "controls",
    "copilot_feedback",
    "copilot_messages",
    "dark_room_snapshots",
    "data_catalog_entries",
    "data_processing_activities",
    "data_processing_agreements",
    "data_transfer_log",
    "epistemic_frames",
    "evidence_items",
    "export_logs",
    "financial_assumptions",
    "gap_analysis_results",
    "gap_findings",
    "golden_eval_results",
    "grading_snapshots",
    "graph_health_snapshots",
    "illumination_actions",
    "incidents",
    "integration_connections",
    "maturity_scores",
    "metric_readings",
    "micro_surveys",
    "monitoring_alerts",
    "monitoring_jobs",
    "ontology_versions",
    "pattern_access_rules",
    "pdp_audit_entries",
    "pii_quarantine",
    "pipeline_stage_metrics",
    "policies",
    "process_baselines",
    "process_deviations",
    "process_models",
    "raci_cells",
    "regulations",
    "rejection_feedback",
    "reports",
    "retention_policies",
    "review_packs",
    "role_activity_mappings",
    "seed_terms",
    "semantic_relationships",
    "shelf_data_requests",
    "simulation_scenarios",
    "standard_contractual_clauses",
    "survey_claims",
    "survey_sessions",
    "switching_traces",
    "target_operating_models",
    "task_mining_actions",
    "task_mining_agents",
    "task_mining_events",
    "task_mining_sessions",
    "tom_alignment_runs",
    "transfer_impact_assessments",
    "transformation_roadmaps",
    "transition_matrices",
    "uplift_projections",
    "validation_decisions",
    "visual_context_events",
]


async def set_engagement_context(
    session: AsyncSession,
    engagement_id: UUID,
) -> None:
    """Set the current engagement context for RLS filtering.

    Uses ``set_config(..., true)`` so the variable is scoped to the current
    transaction and automatically reset on commit or rollback.  Unlike
    ``SET LOCAL``, ``set_config`` is a regular SQL function and supports
    parameterized queries (required by asyncpg).

    Args:
        session: The async database session.
        engagement_id: The engagement UUID to scope queries to.
    """
    await session.execute(
        text("SELECT set_config(:var, :eid, true)"),
        {"var": RLS_SESSION_VAR, "eid": str(engagement_id)},
    )
    logger.debug("RLS context set to engagement %s", engagement_id)


async def clear_engagement_context(session: AsyncSession) -> None:
    """Clear the current engagement context.

    Resets the session variable so no engagement filter is applied.
    Useful for admin operations that need to see all data.

    Args:
        session: The async database session.
    """
    await session.execute(text(f"RESET {RLS_SESSION_VAR}"))
    logger.debug("RLS context cleared")


async def set_rls_bypass(session: AsyncSession, bypass: bool = True) -> None:
    """Enable or disable RLS bypass for admin operations.

    Uses SET LOCAL row_security to control RLS enforcement for the
    current transaction. Requires the database role to have BYPASSRLS
    privilege, or the session must be running as a superuser.

    Args:
        session: The async database session.
        bypass: True to disable RLS (admin mode), False to re-enable.
    """
    value = "off" if bypass else "on"
    await session.execute(text(f"SET LOCAL row_security = {value}"))
    logger.debug("RLS bypass set to %s", bypass)


def _validate_table_name(table_name: str) -> None:
    """Validate table name to prevent SQL injection in DDL generation.

    Args:
        table_name: The table name to validate.

    Raises:
        ValueError: If the table name contains invalid characters.
    """
    if not _TABLE_NAME_RE.match(table_name):
        msg = f"Invalid table name: {table_name!r} (must match [a-z_][a-z0-9_]*)"
        raise ValueError(msg)


def apply_engagement_rls(table_name: str) -> list[str]:
    """Generate SQL statements to apply RLS to an engagement-scoped table.

    Returns DDL statements that:
    1. Enable RLS on the table
    2. Force RLS even for table owners
    3. Create a SELECT policy filtering by engagement_id
    4. Create an INSERT policy ensuring new rows match context
    5. Create an UPDATE policy with USING + WITH CHECK (prevents engagement_id mutation)
    6. Create a DELETE policy filtering by engagement_id

    Args:
        table_name: The table to apply RLS to.

    Returns:
        List of SQL DDL strings to execute.

    Raises:
        ValueError: If table_name contains invalid characters.
    """
    _validate_table_name(table_name)

    policy_name = f"engagement_isolation_{table_name}"
    rls_condition = f"engagement_id = NULLIF(current_setting('{RLS_SESSION_VAR}', true), '')::uuid"

    return [
        f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY",
        # SELECT: can only see rows for current engagement
        (f"CREATE POLICY {policy_name}_select ON {table_name} FOR SELECT USING ({rls_condition})"),
        # INSERT: can only insert rows for current engagement
        (f"CREATE POLICY {policy_name}_insert ON {table_name} FOR INSERT WITH CHECK ({rls_condition})"),
        # UPDATE: USING controls visibility, WITH CHECK prevents engagement_id mutation
        (
            f"CREATE POLICY {policy_name}_update ON {table_name} "
            f"FOR UPDATE USING ({rls_condition}) WITH CHECK ({rls_condition})"
        ),
        # DELETE: can only delete rows for current engagement
        (f"CREATE POLICY {policy_name}_delete ON {table_name} FOR DELETE USING ({rls_condition})"),
    ]


def remove_engagement_rls(table_name: str) -> list[str]:
    """Generate SQL statements to remove RLS from a table.

    Args:
        table_name: The table to remove RLS from.

    Returns:
        List of SQL DDL strings to execute.

    Raises:
        ValueError: If table_name contains invalid characters.
    """
    _validate_table_name(table_name)

    policy_name = f"engagement_isolation_{table_name}"

    return [
        f"DROP POLICY IF EXISTS {policy_name}_select ON {table_name}",
        f"DROP POLICY IF EXISTS {policy_name}_insert ON {table_name}",
        f"DROP POLICY IF EXISTS {policy_name}_update ON {table_name}",
        f"DROP POLICY IF EXISTS {policy_name}_delete ON {table_name}",
        f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY",
    ]
