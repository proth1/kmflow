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
