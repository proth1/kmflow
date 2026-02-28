"""BDD tests for Row-Level Security (RLS) engagement data isolation.

Story #311: Engagement-Level Data Isolation via PostgreSQL Row-Level Security.

Tests the RLS helper module: session context management, policy generation,
admin bypass, and table coverage.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from src.core.rls import (
    ENGAGEMENT_SCOPED_TABLES,
    RLS_SESSION_VAR,
    apply_engagement_rls,
    clear_engagement_context,
    remove_engagement_rls,
    set_engagement_context,
    set_rls_bypass,
)

# ---------------------------------------------------------------------------
# Scenario: User sees only their own engagement's evidence
# ---------------------------------------------------------------------------


class TestEngagementContextSetting:
    """Verify that setting engagement context issues correct SQL."""

    @pytest.mark.asyncio
    async def test_set_engagement_context_executes_set_local(self) -> None:
        """SET LOCAL should be called with the engagement UUID."""
        session = AsyncMock()
        eid = uuid.uuid4()

        await set_engagement_context(session, eid)

        session.execute.assert_called_once()
        call_args = session.execute.call_args
        sql_text = str(call_args[0][0])
        assert "SET LOCAL" in sql_text
        assert RLS_SESSION_VAR in sql_text
        assert call_args[1] == {"eid": str(eid)} or call_args[0][1] == {"eid": str(eid)}

    @pytest.mark.asyncio
    async def test_set_engagement_context_uses_transaction_scoped_variable(self) -> None:
        """SET LOCAL ensures variable resets on commit/rollback."""
        session = AsyncMock()
        eid = uuid.uuid4()

        await set_engagement_context(session, eid)

        sql_text = str(session.execute.call_args[0][0])
        # SET LOCAL is transaction-scoped (vs SET which is session-scoped)
        assert "SET LOCAL" in sql_text

    @pytest.mark.asyncio
    async def test_clear_engagement_context_resets_variable(self) -> None:
        """RESET should clear the session variable."""
        session = AsyncMock()

        await clear_engagement_context(session)

        session.execute.assert_called_once()
        sql_text = str(session.execute.call_args[0][0])
        assert "RESET" in sql_text
        assert RLS_SESSION_VAR in sql_text

    @pytest.mark.asyncio
    async def test_set_context_accepts_uuid_object(self) -> None:
        """Should accept UUID objects, converting to string for SQL."""
        session = AsyncMock()
        eid = uuid.UUID("12345678-1234-5678-1234-567812345678")

        await set_engagement_context(session, eid)

        call_args = session.execute.call_args
        # Verify the UUID was passed as a string parameter
        params = call_args[1] if call_args[1] else call_args[0][1]
        assert params["eid"] == "12345678-1234-5678-1234-567812345678"


# ---------------------------------------------------------------------------
# Scenario: RLS enforces isolation even with direct SQL access
# ---------------------------------------------------------------------------


class TestRlsPolicyGeneration:
    """Verify that RLS DDL generation produces correct policies."""

    def test_apply_rls_generates_enable_statement(self) -> None:
        """ENABLE ROW LEVEL SECURITY must be in the generated DDL."""
        stmts = apply_engagement_rls("evidence_items")

        enable_stmts = [s for s in stmts if "ENABLE ROW LEVEL SECURITY" in s]
        assert len(enable_stmts) == 1
        assert "evidence_items" in enable_stmts[0]

    def test_apply_rls_generates_force_statement(self) -> None:
        """FORCE ROW LEVEL SECURITY ensures table owners also obey policies."""
        stmts = apply_engagement_rls("evidence_items")

        force_stmts = [s for s in stmts if "FORCE ROW LEVEL SECURITY" in s]
        assert len(force_stmts) == 1

    def test_apply_rls_creates_four_policies(self) -> None:
        """Four CRUD policies (SELECT, INSERT, UPDATE, DELETE) should be created."""
        stmts = apply_engagement_rls("evidence_items")

        policy_stmts = [s for s in stmts if "CREATE POLICY" in s]
        assert len(policy_stmts) == 4

        operations = {"SELECT", "INSERT", "UPDATE", "DELETE"}
        found_ops = set()
        for stmt in policy_stmts:
            for op in operations:
                if f"FOR {op}" in stmt:
                    found_ops.add(op)
        assert found_ops == operations

    def test_select_policy_uses_using_clause(self) -> None:
        """SELECT policy should use USING clause for read filtering."""
        stmts = apply_engagement_rls("evidence_items")

        select_policy = [s for s in stmts if "FOR SELECT" in s][0]
        assert "USING" in select_policy
        assert "current_setting" in select_policy
        assert RLS_SESSION_VAR in select_policy

    def test_insert_policy_uses_with_check(self) -> None:
        """INSERT policy should use WITH CHECK to validate new rows."""
        stmts = apply_engagement_rls("evidence_items")

        insert_policy = [s for s in stmts if "FOR INSERT" in s][0]
        assert "WITH CHECK" in insert_policy
        assert "current_setting" in insert_policy

    def test_policy_references_engagement_id_column(self) -> None:
        """All policies should filter on the engagement_id column."""
        stmts = apply_engagement_rls("process_models")

        policy_stmts = [s for s in stmts if "CREATE POLICY" in s]
        for stmt in policy_stmts:
            assert "engagement_id" in stmt

    def test_policy_casts_to_uuid(self) -> None:
        """Session variable should be cast to UUID type."""
        stmts = apply_engagement_rls("evidence_items")

        select_policy = [s for s in stmts if "FOR SELECT" in s][0]
        assert "::uuid" in select_policy

    def test_policy_naming_convention(self) -> None:
        """Policies should follow engagement_isolation_{table}_{operation} naming."""
        stmts = apply_engagement_rls("seed_terms")

        policy_stmts = [s for s in stmts if "CREATE POLICY" in s]
        for stmt in policy_stmts:
            assert "engagement_isolation_seed_terms_" in stmt

    def test_remove_rls_drops_all_policies(self) -> None:
        """Removing RLS should drop all 4 policies and disable RLS."""
        stmts = remove_engagement_rls("evidence_items")

        drop_stmts = [s for s in stmts if "DROP POLICY" in s]
        assert len(drop_stmts) == 4

        disable_stmts = [s for s in stmts if "DISABLE ROW LEVEL SECURITY" in s]
        assert len(disable_stmts) == 1

        no_force = [s for s in stmts if "NO FORCE" in s]
        assert len(no_force) == 1

    def test_remove_uses_if_exists(self) -> None:
        """DROP POLICY should use IF EXISTS for idempotency."""
        stmts = remove_engagement_rls("evidence_items")

        drop_stmts = [s for s in stmts if "DROP POLICY" in s]
        for stmt in drop_stmts:
            assert "IF EXISTS" in stmt


# ---------------------------------------------------------------------------
# Scenario: Multi-engagement user sees all authorized engagements
# ---------------------------------------------------------------------------


class TestMultiEngagementContext:
    """Verify that context can be changed between engagements."""

    @pytest.mark.asyncio
    async def test_context_can_be_switched(self) -> None:
        """Setting context twice should issue two SET LOCAL calls."""
        session = AsyncMock()
        eid1 = uuid.uuid4()
        eid2 = uuid.uuid4()

        await set_engagement_context(session, eid1)
        await set_engagement_context(session, eid2)

        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_each_context_uses_different_uuid(self) -> None:
        """Each SET LOCAL should use the respective engagement UUID."""
        session = AsyncMock()
        eid1 = uuid.uuid4()
        eid2 = uuid.uuid4()

        await set_engagement_context(session, eid1)
        await set_engagement_context(session, eid2)

        calls = session.execute.call_args_list
        params1 = calls[0][1] if calls[0][1] else calls[0][0][1]
        params2 = calls[1][1] if calls[1][1] else calls[1][0][1]
        assert params1["eid"] == str(eid1)
        assert params2["eid"] == str(eid2)


# ---------------------------------------------------------------------------
# Scenario: Admin user can access all engagements
# ---------------------------------------------------------------------------


class TestAdminBypass:
    """Verify admin bypass mechanism for RLS."""

    @pytest.mark.asyncio
    async def test_set_rls_bypass_disables_row_security(self) -> None:
        """Bypass should SET LOCAL row_security = off."""
        session = AsyncMock()

        await set_rls_bypass(session, bypass=True)

        session.execute.assert_called_once()
        sql_text = str(session.execute.call_args[0][0])
        assert "row_security" in sql_text
        assert "off" in sql_text

    @pytest.mark.asyncio
    async def test_rls_bypass_can_be_re_enabled(self) -> None:
        """Re-enabling should SET LOCAL row_security = on."""
        session = AsyncMock()

        await set_rls_bypass(session, bypass=False)

        sql_text = str(session.execute.call_args[0][0])
        assert "row_security" in sql_text
        assert " on" in sql_text

    @pytest.mark.asyncio
    async def test_bypass_uses_set_local(self) -> None:
        """Bypass should use SET LOCAL (transaction-scoped), not SET."""
        session = AsyncMock()

        await set_rls_bypass(session, bypass=True)

        sql_text = str(session.execute.call_args[0][0])
        assert "SET LOCAL" in sql_text


# ---------------------------------------------------------------------------
# Scenario: New table automatically receives RLS policies
# ---------------------------------------------------------------------------


class TestRlsTableCoverage:
    """Verify all engagement-scoped tables are covered by RLS."""

    def test_engagement_scoped_tables_not_empty(self) -> None:
        """Must have at least the core engagement-scoped tables."""
        assert len(ENGAGEMENT_SCOPED_TABLES) >= 15

    def test_evidence_items_in_scoped_tables(self) -> None:
        """evidence_items is the primary evidence table and must be covered."""
        assert "evidence_items" in ENGAGEMENT_SCOPED_TABLES

    def test_process_models_in_scoped_tables(self) -> None:
        """process_models stores POV output and must be covered."""
        assert "process_models" in ENGAGEMENT_SCOPED_TABLES

    def test_audit_logs_in_scoped_tables(self) -> None:
        """audit_logs have nullable engagement_id and should be covered."""
        assert "audit_logs" in ENGAGEMENT_SCOPED_TABLES

    def test_shelf_data_requests_in_scoped_tables(self) -> None:
        """shelf_data_requests contain client evidence requests."""
        assert "shelf_data_requests" in ENGAGEMENT_SCOPED_TABLES

    def test_monitoring_tables_in_scoped(self) -> None:
        """Monitoring-related tables must be engagement-scoped."""
        monitoring_tables = {
            "monitoring_jobs",
            "monitoring_alerts",
            "metric_readings",
            "process_baselines",
            "process_deviations",
        }
        for table in monitoring_tables:
            assert table in ENGAGEMENT_SCOPED_TABLES, f"{table} missing from ENGAGEMENT_SCOPED_TABLES"

    def test_governance_tables_in_scoped(self) -> None:
        """Governance tables must be engagement-scoped."""
        governance_tables = {"policies", "controls", "regulations"}
        for table in governance_tables:
            assert table in ENGAGEMENT_SCOPED_TABLES, f"{table} missing from ENGAGEMENT_SCOPED_TABLES"

    def test_simulation_tables_in_scoped(self) -> None:
        """Simulation tables must be engagement-scoped."""
        assert "simulation_scenarios" in ENGAGEMENT_SCOPED_TABLES
        assert "financial_assumptions" in ENGAGEMENT_SCOPED_TABLES

    def test_tom_tables_in_scoped(self) -> None:
        """TOM and gap analysis tables must be engagement-scoped."""
        assert "target_operating_models" in ENGAGEMENT_SCOPED_TABLES
        assert "gap_analysis_results" in ENGAGEMENT_SCOPED_TABLES

    def test_task_mining_tables_in_scoped(self) -> None:
        """Task mining tables must be engagement-scoped."""
        tm_tables = {"task_mining_agents", "task_mining_sessions", "task_mining_events", "task_mining_actions"}
        for table in tm_tables:
            assert table in ENGAGEMENT_SCOPED_TABLES, f"{table} missing from ENGAGEMENT_SCOPED_TABLES"

    def test_survey_tables_in_scoped(self) -> None:
        """Survey and epistemic frame tables must be engagement-scoped."""
        assert "survey_claims" in ENGAGEMENT_SCOPED_TABLES
        assert "epistemic_frames" in ENGAGEMENT_SCOPED_TABLES

    def test_pii_quarantine_in_scoped(self) -> None:
        """PII quarantine table must be engagement-scoped."""
        assert "pii_quarantine" in ENGAGEMENT_SCOPED_TABLES

    def test_tables_are_sorted(self) -> None:
        """Table list should be alphabetically sorted for consistency."""
        assert sorted(ENGAGEMENT_SCOPED_TABLES) == ENGAGEMENT_SCOPED_TABLES

    def test_no_duplicate_tables(self) -> None:
        """No table should appear twice in the list."""
        assert len(ENGAGEMENT_SCOPED_TABLES) == len(set(ENGAGEMENT_SCOPED_TABLES))


# ---------------------------------------------------------------------------
# Scenario: Migration helper generates correct DDL
# ---------------------------------------------------------------------------


class TestMigrationHelper:
    """Verify the Alembic migration helper produces correct DDL."""

    def test_apply_returns_six_statements(self) -> None:
        """Each table gets ENABLE, FORCE, and 4 CRUD policies = 6 statements."""
        stmts = apply_engagement_rls("test_table")
        assert len(stmts) == 6

    def test_remove_returns_six_statements(self) -> None:
        """Removal: 4 DROP POLICY + DISABLE + NO FORCE = 6 statements."""
        stmts = remove_engagement_rls("test_table")
        assert len(stmts) == 6

    def test_apply_and_remove_are_inverse(self) -> None:
        """Every policy created by apply should be dropped by remove."""
        apply_stmts = apply_engagement_rls("test_table")
        remove_stmts = remove_engagement_rls("test_table")

        # Extract policy names from CREATE statements
        created_policies = set()
        for stmt in apply_stmts:
            if "CREATE POLICY" in stmt:
                # "CREATE POLICY engagement_isolation_test_table_select ON ..."
                name = stmt.split("CREATE POLICY ")[1].split(" ON")[0]
                created_policies.add(name)

        # Extract policy names from DROP statements
        dropped_policies = set()
        for stmt in remove_stmts:
            if "DROP POLICY" in stmt:
                name = stmt.split("DROP POLICY IF EXISTS ")[1].split(" ON")[0]
                dropped_policies.add(name)

        assert created_policies == dropped_policies

    def test_all_scoped_tables_generate_valid_ddl(self) -> None:
        """Every table in the scoped list should produce valid DDL."""
        for table in ENGAGEMENT_SCOPED_TABLES:
            stmts = apply_engagement_rls(table)
            assert len(stmts) == 6, f"{table} did not generate 6 statements"
            assert any("ENABLE" in s for s in stmts)
            assert any("FORCE" in s for s in stmts)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestRlsEdgeCases:
    """Edge cases for RLS helpers."""

    @pytest.mark.asyncio
    async def test_set_context_with_nil_uuid(self) -> None:
        """Should handle nil UUID (all zeros) without error."""
        session = AsyncMock()
        nil_uuid = uuid.UUID("00000000-0000-0000-0000-000000000000")

        await set_engagement_context(session, nil_uuid)

        params = session.execute.call_args[1] if session.execute.call_args[1] else session.execute.call_args[0][1]
        assert params["eid"] == "00000000-0000-0000-0000-000000000000"

    def test_rls_session_var_name(self) -> None:
        """Session variable name should be app.current_engagement_id."""
        assert RLS_SESSION_VAR == "app.current_engagement_id"

    def test_apply_rls_different_tables_have_different_policy_names(self) -> None:
        """Each table should have uniquely named policies."""
        stmts_a = apply_engagement_rls("table_a")
        stmts_b = apply_engagement_rls("table_b")

        policies_a = {s for s in stmts_a if "CREATE POLICY" in s}
        policies_b = {s for s in stmts_b if "CREATE POLICY" in s}

        # No policy statement should be the same between two different tables
        assert not policies_a.intersection(policies_b)


# ---------------------------------------------------------------------------
# Table name validation (SQL injection prevention)
# ---------------------------------------------------------------------------


class TestTableNameValidation:
    """Verify table name validation prevents SQL injection."""

    def test_valid_table_name_accepted(self) -> None:
        """Valid PostgreSQL table names should be accepted."""
        stmts = apply_engagement_rls("evidence_items")
        assert len(stmts) == 6

    def test_sql_injection_rejected(self) -> None:
        """Table names with SQL injection should be rejected."""
        with pytest.raises(ValueError, match="Invalid table name"):
            apply_engagement_rls("evidence_items; DROP TABLE users")

    def test_uppercase_rejected(self) -> None:
        """Uppercase table names should be rejected."""
        with pytest.raises(ValueError, match="Invalid table name"):
            apply_engagement_rls("EvidenceItems")

    def test_hyphen_rejected(self) -> None:
        """Hyphens in table names should be rejected."""
        with pytest.raises(ValueError, match="Invalid table name"):
            apply_engagement_rls("evidence-items")

    def test_space_rejected(self) -> None:
        """Spaces in table names should be rejected."""
        with pytest.raises(ValueError, match="Invalid table name"):
            apply_engagement_rls("evidence items")

    def test_empty_string_rejected(self) -> None:
        """Empty table name should be rejected."""
        with pytest.raises(ValueError, match="Invalid table name"):
            apply_engagement_rls("")

    def test_remove_also_validates(self) -> None:
        """remove_engagement_rls should also validate table names."""
        with pytest.raises(ValueError, match="Invalid table name"):
            remove_engagement_rls("DROP TABLE users;")


# ---------------------------------------------------------------------------
# UPDATE policy WITH CHECK clause
# ---------------------------------------------------------------------------


class TestUpdatePolicyWithCheck:
    """Verify UPDATE policy prevents engagement_id mutation."""

    def test_update_policy_has_with_check(self) -> None:
        """UPDATE policy must have WITH CHECK to prevent engagement_id mutation."""
        stmts = apply_engagement_rls("evidence_items")
        update_policy = [s for s in stmts if "FOR UPDATE" in s][0]
        assert "WITH CHECK" in update_policy

    def test_update_policy_has_using_and_with_check(self) -> None:
        """UPDATE policy should have both USING (visibility) and WITH CHECK (mutation)."""
        stmts = apply_engagement_rls("evidence_items")
        update_policy = [s for s in stmts if "FOR UPDATE" in s][0]
        assert "USING" in update_policy
        assert "WITH CHECK" in update_policy

    def test_update_with_check_references_same_condition(self) -> None:
        """Both USING and WITH CHECK should reference the same RLS condition."""
        stmts = apply_engagement_rls("evidence_items")
        update_policy = [s for s in stmts if "FOR UPDATE" in s][0]
        # Should contain the condition twice (once in USING, once in WITH CHECK)
        assert update_policy.count("current_setting") == 2
