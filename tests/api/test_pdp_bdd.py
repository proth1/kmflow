"""BDD tests for Story #377: Policy Decision Point (PDP) Service.

Tests policy evaluation, rule management, audit trail, and health metrics.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.services.pdp import PDPService, _recent_latencies
from src.core.models import UserRole
from src.core.models.pdp import (
    DEFAULT_POLICIES,
    ObligationType,
    OperationType,
    PDPDecisionType,
    PDPPolicy,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid.uuid4()


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _setup_policies(session: AsyncMock, policies: list[dict]) -> None:
    """Set up mock session to return given policies from execute()."""
    mock_policies = []
    for p in policies:
        policy = MagicMock(spec=PDPPolicy)
        policy.id = p.get("id", uuid.uuid4())
        policy.name = p["name"]
        policy.conditions_json = p["conditions_json"]
        policy.decision = PDPDecisionType(p["decision"]) if isinstance(p["decision"], str) else p["decision"]
        policy.obligations_json = p.get("obligations_json")
        policy.reason = p.get("reason")
        policy.priority = p.get("priority", 100)
        policy.is_active = True
        mock_policies.append(policy)

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = mock_policies
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)


def _invalidate_cache() -> None:
    """Force cache refresh for test isolation."""
    import src.api.services.pdp as pdp_mod

    pdp_mod._cache_loaded_at = 0.0
    pdp_mod._policy_cache.clear()


# ---------------------------------------------------------------------------
# BDD Scenario 1: Restricted evidence denied for non-authorized role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_1_restricted_denied_for_process_analyst() -> None:
    """Given RESTRICTED evidence and PROCESS_ANALYST role,
    When PDP evaluates access request,
    Then decision is DENY with reason=insufficient_clearance."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(session, DEFAULT_POLICIES)

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="analyst@example.com",
        actor_role=UserRole.PROCESS_ANALYST.value,
        resource_id="evidence-001",
        classification="restricted",
        operation="read",
    )

    assert result["decision"] == PDPDecisionType.DENY
    assert result["reason"] == "insufficient_clearance"
    assert result["required_role"] == UserRole.ENGAGEMENT_LEAD.value
    assert "audit_id" in result
    session.add.assert_called()


@pytest.mark.asyncio
async def test_scenario_1_restricted_denied_for_evidence_reviewer() -> None:
    """Evidence reviewers also cannot access RESTRICTED data."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(session, DEFAULT_POLICIES)

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="reviewer@example.com",
        actor_role=UserRole.EVIDENCE_REVIEWER.value,
        resource_id="evidence-002",
        classification="restricted",
        operation="read",
    )

    assert result["decision"] == PDPDecisionType.DENY
    assert result["reason"] == "insufficient_clearance"


@pytest.mark.asyncio
async def test_scenario_1_restricted_permitted_for_engagement_lead() -> None:
    """Engagement leads CAN access RESTRICTED data (with enhanced audit)."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(session, DEFAULT_POLICIES)

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="lead@example.com",
        actor_role=UserRole.ENGAGEMENT_LEAD.value,
        resource_id="evidence-003",
        classification="restricted",
        operation="read",
    )

    assert result["decision"] == PDPDecisionType.PERMIT
    assert result["reason"] == "access_permitted_with_enhanced_audit"
    assert any(o.get("type") == ObligationType.LOG_ENHANCED_AUDIT for o in result["obligations"])


# ---------------------------------------------------------------------------
# BDD Scenario 2: Confidential export with watermark obligation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_2_confidential_export_with_watermark() -> None:
    """Given CONFIDENTIAL evidence and ENGAGEMENT_LEAD exporting,
    When PDP evaluates export request,
    Then decision is PERMIT with apply_watermark obligation."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(session, DEFAULT_POLICIES)

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="lead@example.com",
        actor_role=UserRole.ENGAGEMENT_LEAD.value,
        resource_id="evidence-004",
        classification="confidential",
        operation="export",
    )

    assert result["decision"] == PDPDecisionType.PERMIT
    assert result["reason"] == "export_permitted_with_watermark"
    assert any(o.get("type") == ObligationType.APPLY_WATERMARK for o in result["obligations"])


@pytest.mark.asyncio
async def test_scenario_2_confidential_read_no_watermark() -> None:
    """Reading confidential data does not require watermark."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(session, DEFAULT_POLICIES)

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="lead@example.com",
        actor_role=UserRole.ENGAGEMENT_LEAD.value,
        resource_id="evidence-005",
        classification="confidential",
        operation="read",
    )

    assert result["decision"] == PDPDecisionType.PERMIT
    # No watermark obligation for read
    watermark_obligations = [o for o in result["obligations"] if o.get("type") == ObligationType.APPLY_WATERMARK]
    assert len(watermark_obligations) == 0


# ---------------------------------------------------------------------------
# BDD Scenario 3: Hot-reload — new rule takes effect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_3_new_rule_active_after_creation() -> None:
    """Given PDP is running,
    When new policy rule is created,
    Then it is active for subsequent evaluations."""
    _invalidate_cache()
    session = _mock_session()

    service = PDPService(session)
    policy = await service.create_rule(
        name="block_delete_public",
        description="Block delete on public data",
        conditions_json={"classification": "public", "operation": "delete"},
        decision=PDPDecisionType.DENY,
        reason="delete_not_allowed_on_public",
        priority=5,
    )

    assert policy.name == "block_delete_public"
    assert policy.decision == PDPDecisionType.DENY
    assert policy.is_active is True
    session.add.assert_called()


# ---------------------------------------------------------------------------
# BDD Scenario 4: Audit trail for every decision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_4_audit_entry_created() -> None:
    """Given PDP evaluates a request,
    When decision is returned,
    Then an audit entry is created with full context."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(session, DEFAULT_POLICIES)

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="analyst@example.com",
        actor_role=UserRole.PROCESS_ANALYST.value,
        resource_id="evidence-006",
        classification="internal",
        operation="read",
        request_id="req-12345",
    )

    assert "audit_id" in result
    # Verify session.add was called (audit entry written)
    assert session.add.call_count >= 1


@pytest.mark.asyncio
async def test_scenario_4_audit_includes_request_id() -> None:
    """Audit entry includes request_id when provided."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(session, DEFAULT_POLICIES)

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="lead@example.com",
        actor_role=UserRole.ENGAGEMENT_LEAD.value,
        resource_id="evidence-007",
        classification="public",
        operation="read",
        request_id="trace-abc",
    )

    assert result["decision"] == PDPDecisionType.PERMIT
    assert "audit_id" in result


# ---------------------------------------------------------------------------
# BDD Scenario 5: Health check with latency metrics
# ---------------------------------------------------------------------------


def test_scenario_5_health_empty() -> None:
    """Health check with no decisions returns zero metrics."""
    _recent_latencies.clear()
    metrics = PDPService.get_health_metrics()

    assert metrics["status"] == "healthy"
    assert metrics["decisions_tracked"] == 0
    assert metrics["p99_latency_ms"] == 0.0


@pytest.mark.asyncio
async def test_scenario_5_health_tracks_latency() -> None:
    """After evaluations, health shows tracked p99 latency."""
    _invalidate_cache()
    _recent_latencies.clear()
    session = _mock_session()
    _setup_policies(session, DEFAULT_POLICIES)

    service = PDPService(session)

    # Run a few evaluations to populate latency tracking
    for _ in range(5):
        await service.evaluate(
            engagement_id=ENGAGEMENT_ID,
            actor="user@example.com",
            actor_role=UserRole.ENGAGEMENT_LEAD.value,
            resource_id="evidence-008",
            classification="public",
            operation="read",
        )

    metrics = PDPService.get_health_metrics()
    assert metrics["decisions_tracked"] == 5
    assert metrics["p99_latency_ms"] >= 0
    assert "avg_latency_ms" in metrics


# ---------------------------------------------------------------------------
# Additional: Public/Internal data always permitted (default)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_data_always_permitted() -> None:
    """Public data access is always permitted (no matching deny rule)."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(session, DEFAULT_POLICIES)

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="viewer@example.com",
        actor_role=UserRole.CLIENT_VIEWER.value,
        resource_id="evidence-009",
        classification="public",
        operation="read",
    )

    assert result["decision"] == PDPDecisionType.PERMIT


@pytest.mark.asyncio
async def test_internal_data_permitted_for_analyst() -> None:
    """Internal data is permitted for process analysts."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(session, DEFAULT_POLICIES)

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="analyst@example.com",
        actor_role=UserRole.PROCESS_ANALYST.value,
        resource_id="evidence-010",
        classification="internal",
        operation="write",
    )

    assert result["decision"] == PDPDecisionType.PERMIT


# ---------------------------------------------------------------------------
# Unit tests: enums and defaults
# ---------------------------------------------------------------------------


def test_pdp_decision_enum_values() -> None:
    """PDPDecisionType has correct values."""
    assert PDPDecisionType.PERMIT == "permit"
    assert PDPDecisionType.DENY == "deny"


def test_obligation_type_enum_values() -> None:
    """ObligationType has correct values."""
    assert ObligationType.APPLY_WATERMARK == "apply_watermark"
    assert ObligationType.LOG_ENHANCED_AUDIT == "log_enhanced_audit"
    assert ObligationType.REQUIRE_MFA == "require_mfa"
    assert ObligationType.REDACT_FIELDS == "redact_fields"


def test_operation_type_enum_values() -> None:
    """OperationType has correct values."""
    assert OperationType.READ == "read"
    assert OperationType.EXPORT == "export"
    assert OperationType.DELETE == "delete"


def test_default_policies_count() -> None:
    """Default policies include the expected rules."""
    assert len(DEFAULT_POLICIES) == 3
    names = [p["name"] for p in DEFAULT_POLICIES]
    assert "deny_restricted_below_lead" in names
    assert "watermark_confidential_export" in names
    assert "enhanced_audit_restricted" in names


# ---------------------------------------------------------------------------
# List rules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_rules() -> None:
    """List rules returns active policies."""
    session = _mock_session()
    policies = [MagicMock(spec=PDPPolicy) for _ in range(2)]
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = policies
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)

    service = PDPService(session)
    result = await service.list_rules()
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Conditions validation (SEC-2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rule_rejects_unknown_condition_keys() -> None:
    """Creating a rule with unknown condition keys raises ValueError."""
    session = _mock_session()
    service = PDPService(session)

    with pytest.raises(ValueError, match="Unknown condition keys"):
        await service.create_rule(
            name="bad_rule",
            conditions_json={"clasification": "restricted", "unknown_key": "value"},
            decision=PDPDecisionType.DENY,
        )


@pytest.mark.asyncio
async def test_create_rule_accepts_valid_condition_keys() -> None:
    """Creating a rule with only valid condition keys succeeds."""
    session = _mock_session()
    service = PDPService(session)

    policy = await service.create_rule(
        name="valid_rule",
        conditions_json={"classification": "restricted", "operation": "read", "max_role": "process_analyst"},
        decision=PDPDecisionType.DENY,
        reason="test",
    )

    assert policy.name == "valid_rule"


# ---------------------------------------------------------------------------
# ABAC: department condition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abac_department_condition_deny() -> None:
    """Given a DENY policy for 'finance' department, a finance user is denied.

    ABAC conditions match when the request attribute equals the condition value.
    A policy with {"department": "finance"} fires exactly when the requester
    belongs to the 'finance' department.
    """
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(
        session,
        [
            {
                "name": "deny_finance_department",
                "conditions_json": {"department": "finance"},
                "decision": PDPDecisionType.DENY,
                "reason": "finance_access_blocked",
                "priority": 5,
            }
        ],
    )

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="user@example.com",
        actor_role=UserRole.ENGAGEMENT_LEAD.value,
        resource_id="resource-001",
        classification="internal",
        operation="read",
        attributes={"department": "finance"},
    )

    assert result["decision"] == PDPDecisionType.DENY
    assert result["reason"] == "finance_access_blocked"


@pytest.mark.asyncio
async def test_abac_department_condition_permit_when_not_matching() -> None:
    """User from 'hr' is permitted when the deny policy targets 'finance' department only."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(
        session,
        [
            {
                "name": "deny_finance_only",
                "conditions_json": {"department": "finance"},
                "decision": PDPDecisionType.DENY,
                "reason": "finance_blocked",
                "priority": 5,
            }
        ],
    )

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="hr@example.com",
        actor_role=UserRole.ENGAGEMENT_LEAD.value,
        resource_id="resource-002",
        classification="internal",
        operation="read",
        attributes={"department": "hr"},  # does NOT match "finance" → no deny rule matches
    )

    assert result["decision"] == PDPDecisionType.PERMIT


# ---------------------------------------------------------------------------
# ABAC: cohort_size threshold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abac_cohort_size_below_threshold_fires_obligation() -> None:
    """A policy with cohort_size_lt condition matches when cohort is below threshold."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(
        session,
        [
            {
                "name": "suppress_small_cohort",
                "conditions_json": {"cohort_size_lt": 5},
                "decision": PDPDecisionType.PERMIT,
                "obligations_json": [{"type": "suppress_cohort", "params": {"min_cohort": 5}}],
                "reason": "cohort_suppressed",
                "priority": 10,
            }
        ],
    )

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="analyst@example.com",
        actor_role=UserRole.PROCESS_ANALYST.value,
        resource_id="agg-001",
        classification="internal",
        operation="read",
        attributes={"cohort_size": 3},
    )

    assert result["decision"] == PDPDecisionType.PERMIT
    assert any(o.get("type") == "suppress_cohort" for o in result["obligations"])


@pytest.mark.asyncio
async def test_abac_cohort_size_above_threshold_no_match() -> None:
    """cohort_size_lt condition does not match when cohort is at or above threshold."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(
        session,
        [
            {
                "name": "suppress_small_cohort",
                "conditions_json": {"cohort_size_lt": 5},
                "decision": PDPDecisionType.PERMIT,
                "obligations_json": [{"type": "suppress_cohort", "params": {"min_cohort": 5}}],
                "reason": "cohort_suppressed",
                "priority": 10,
            }
        ],
    )

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="analyst@example.com",
        actor_role=UserRole.PROCESS_ANALYST.value,
        resource_id="agg-002",
        classification="internal",
        operation="read",
        attributes={"cohort_size": 10},
    )

    # Cohort of 10 is NOT < 5, so the policy doesn't match → default PERMIT, no obligations
    assert result["decision"] == PDPDecisionType.PERMIT
    assert result["obligations"] == []


# ---------------------------------------------------------------------------
# ABAC: data_residency check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abac_data_residency_check_deny() -> None:
    """Requests with EU data_residency are denied by a residency policy."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(
        session,
        [
            {
                "name": "block_eu_export",
                "conditions_json": {"data_residency": "EU", "operation": "export"},
                "decision": PDPDecisionType.DENY,
                "reason": "eu_data_export_blocked",
                "priority": 5,
            }
        ],
    )

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="lead@example.com",
        actor_role=UserRole.ENGAGEMENT_LEAD.value,
        resource_id="evidence-eu-001",
        classification="confidential",
        operation="export",
        attributes={"data_residency": "EU"},
    )

    assert result["decision"] == PDPDecisionType.DENY
    assert result["reason"] == "eu_data_export_blocked"


@pytest.mark.asyncio
async def test_abac_data_residency_check_permit_different_region() -> None:
    """US data_residency is not blocked by the EU export policy."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(
        session,
        [
            {
                "name": "block_eu_export",
                "conditions_json": {"data_residency": "EU", "operation": "export"},
                "decision": PDPDecisionType.DENY,
                "reason": "eu_data_export_blocked",
                "priority": 5,
            }
        ],
    )

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="lead@example.com",
        actor_role=UserRole.ENGAGEMENT_LEAD.value,
        resource_id="evidence-us-001",
        classification="confidential",
        operation="export",
        attributes={"data_residency": "US"},
    )

    assert result["decision"] == PDPDecisionType.PERMIT


# ---------------------------------------------------------------------------
# Policy bundle versioning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_policy_bundle_versioning_publish() -> None:
    """Publishing a bundle creates an active bundle record."""

    session = _mock_session()

    # Mock select returning no existing active bundles
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)

    service = PDPService(session)
    bundle = await service.publish_bundle(
        version="2026.03.001",
        name="Initial ABAC bundle",
        published_by="admin@example.com",
    )

    assert bundle.version == "2026.03.001"
    assert bundle.is_active is True
    assert bundle.published_by == "admin@example.com"
    session.add.assert_called()


@pytest.mark.asyncio
async def test_policy_bundle_get_active_bundle() -> None:
    """get_active_bundle returns the active bundle."""
    from src.core.models.pdp import PDPPolicyBundle

    session = _mock_session()

    mock_bundle = MagicMock(spec=PDPPolicyBundle)
    mock_bundle.version = "2026.03.001"
    mock_bundle.is_active = True

    scalar_mock = MagicMock()
    scalar_mock.scalar_one_or_none.return_value = mock_bundle
    session.execute = AsyncMock(return_value=scalar_mock)

    service = PDPService(session)
    result = await service.get_active_bundle()
    assert result is mock_bundle
    assert result.version == "2026.03.001"


# ---------------------------------------------------------------------------
# Obligations returned in PERMIT decisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_obligation_masking_returned_in_permit() -> None:
    """A PERMIT decision returns mask_fields obligation from matched policy."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(
        session,
        [
            {
                "name": "mask_pii_on_export",
                "conditions_json": {"operation": "export"},
                "decision": PDPDecisionType.PERMIT,
                "obligations_json": [{"type": "mask_fields", "params": {"fields": ["ssn", "dob"]}}],
                "reason": "export_with_masking",
                "priority": 10,
            }
        ],
    )

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="lead@example.com",
        actor_role=UserRole.ENGAGEMENT_LEAD.value,
        resource_id="report-001",
        classification="internal",
        operation="export",
    )

    assert result["decision"] == PDPDecisionType.PERMIT
    assert any(o.get("type") == "mask_fields" for o in result["obligations"])
    mask_ob = next(o for o in result["obligations"] if o.get("type") == "mask_fields")
    assert "ssn" in mask_ob["params"]["fields"]


@pytest.mark.asyncio
async def test_obligation_suppression_returned_in_permit() -> None:
    """A PERMIT decision returns suppress_cohort obligation from matched policy."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(
        session,
        [
            {
                "name": "suppress_small_cohorts",
                "conditions_json": {},
                "decision": PDPDecisionType.PERMIT,
                "obligations_json": [{"type": "suppress_cohort", "params": {"min_cohort": 10}}],
                "reason": "cohort_check_required",
                "priority": 50,
            }
        ],
    )

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=ENGAGEMENT_ID,
        actor="analyst@example.com",
        actor_role=UserRole.PROCESS_ANALYST.value,
        resource_id="agg-003",
        classification="internal",
        operation="read",
    )

    assert result["decision"] == PDPDecisionType.PERMIT
    assert any(o.get("type") == "suppress_cohort" for o in result["obligations"])


# ---------------------------------------------------------------------------
# ABAC condition keys validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rule_accepts_abac_department_key() -> None:
    """Creating a rule with ABAC 'department' condition key succeeds."""
    session = _mock_session()
    service = PDPService(session)

    policy = await service.create_rule(
        name="dept_rule",
        conditions_json={"department": "finance"},
        decision=PDPDecisionType.DENY,
        reason="finance_restricted",
    )

    assert policy.name == "dept_rule"


@pytest.mark.asyncio
async def test_create_rule_accepts_abac_data_residency_key() -> None:
    """Creating a rule with ABAC 'data_residency' condition key succeeds."""
    session = _mock_session()
    service = PDPService(session)

    policy = await service.create_rule(
        name="residency_rule",
        conditions_json={"data_residency": "EU", "operation": "export"},
        decision=PDPDecisionType.DENY,
        reason="eu_export_blocked",
    )

    assert policy.name == "residency_rule"


# ---------------------------------------------------------------------------
# New ObligationType enum values
# ---------------------------------------------------------------------------


def test_new_obligation_type_enum_values() -> None:
    """New ABAC ObligationType values are correct."""
    from src.core.models.pdp import ObligationType

    assert ObligationType.MASK_FIELDS == "mask_fields"
    assert ObligationType.SUPPRESS_COHORT == "suppress_cohort"
    assert ObligationType.ENFORCE_FIELD_ALLOWLIST == "enforce_field_allowlist"
    assert ObligationType.APPLY_RETENTION_LIMIT == "apply_retention_limit"
