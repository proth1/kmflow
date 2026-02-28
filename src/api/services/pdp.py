"""Policy Decision Point (PDP) service for access decisions.

Evaluates policy rules against request context (user role, data
classification, engagement scope, operation) and returns structured
PERMIT/DENY decisions with optional obligations.
"""

from __future__ import annotations

import asyncio
import collections
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import UserRole
from src.core.models.evidence import DataClassification
from src.core.models.pdp import (
    PDPAuditEntry,
    PDPDecisionType,
    PDPPolicy,
    PDPPolicyBundle,
    PolicyObligation,
)

logger = logging.getLogger(__name__)

# Role hierarchy for comparison (index 0 = most privileged)
_ROLE_RANK: dict[str, int] = {
    UserRole.PLATFORM_ADMIN.value: 0,
    UserRole.ENGAGEMENT_LEAD.value: 1,
    UserRole.PROCESS_ANALYST.value: 2,
    UserRole.EVIDENCE_REVIEWER.value: 3,
    UserRole.CLIENT_VIEWER.value: 4,
}

# In-memory policy cache for sub-10ms response times
_policy_cache: list[dict[str, Any]] = []
_cache_loaded_at: float = 0.0
_CACHE_TTL_SECONDS = 5.0  # 5s TTL ensures new rules take effect within acceptance criteria window
_cache_lock = asyncio.Lock()

# Latency tracking for health endpoint
_recent_latencies: collections.deque[float] = collections.deque(maxlen=100)

# ABAC string condition keys evaluated against the attributes dict
_ABAC_STRING_CONDITION_KEYS: frozenset[str] = frozenset(
    {"department", "cost_center", "data_residency", "evidence_type", "identity_posture", "export_mode"}
)


class PDPService:
    """Evaluates access policies and records audit decisions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def evaluate(
        self,
        *,
        engagement_id: uuid.UUID,
        actor: str,
        actor_role: str,
        resource_id: str,
        classification: str,
        operation: str,
        attributes: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate an access request against loaded policies.

        Args:
            engagement_id: The engagement context.
            actor: Identity of the requester.
            actor_role: Role of the requester (e.g., "process_analyst").
            resource_id: The resource being accessed.
            classification: Data classification level.
            operation: Operation type (read, write, export, delete).
            attributes: ABAC attribute dict. Supported keys: department,
                cost_center, data_residency, cohort_size, evidence_type,
                identity_posture, export_mode.
            request_id: Optional request trace ID.

        Returns:
            Decision dict with decision, obligations, reason, and audit ID.
        """
        start = time.monotonic()

        # Load policies into cache if stale
        await self._ensure_cache()

        decision = PDPDecisionType.PERMIT
        reason: str | None = None
        obligations: list[dict[str, Any]] = []
        matched_policy_id: uuid.UUID | None = None
        effective_attrs = attributes or {}

        # Evaluate policies in priority order (lowest number first)
        for policy in _policy_cache:
            if self._matches(
                policy,
                actor_role=actor_role,
                classification=classification,
                operation=operation,
                attributes=effective_attrs,
            ):
                decision = PDPDecisionType(policy["decision"])
                reason = policy.get("reason")
                obligations = policy.get("obligations_json") or []
                matched_policy_id = policy.get("id")
                break

        # Record audit entry
        now = datetime.now(UTC)
        audit_entry = PDPAuditEntry(
            id=uuid.uuid4(),
            engagement_id=engagement_id,
            actor=actor,
            resource_id=resource_id,
            classification=classification,
            operation=operation,
            decision=decision,
            obligations_json=obligations if obligations else None,
            reason=reason,
            policy_id=matched_policy_id,
            request_id=request_id,
            created_at=now,
        )
        self._session.add(audit_entry)
        await self._session.flush()

        elapsed_ms = (time.monotonic() - start) * 1000
        _recent_latencies.append(elapsed_ms)

        result: dict[str, Any] = {
            "decision": decision,
            "reason": reason,
            "obligations": obligations,
            "audit_id": str(audit_entry.id),
            "latency_ms": round(elapsed_ms, 2),
        }

        # Add required_role hint for DENY decisions
        if decision == PDPDecisionType.DENY and classification == DataClassification.RESTRICTED.value:
            result["required_role"] = UserRole.ENGAGEMENT_LEAD.value

        return result

    def _matches(
        self,
        policy: dict[str, Any],
        *,
        actor_role: str,
        classification: str,
        operation: str,
        attributes: dict[str, Any] | None = None,
    ) -> bool:
        """Check if a policy's conditions match the request context.

        Supports both RBAC conditions (classification, operation, min_role, max_role)
        and ABAC conditions (department, cost_center, data_residency, cohort_size,
        evidence_type, identity_posture, export_mode).

        Note: Policies are currently global (not engagement-scoped). Engagement-scoped
        policy conditions are deferred to a follow-up issue.
        """
        conditions = policy.get("conditions_json", {})
        attrs = attributes or {}

        # Classification match
        if "classification" in conditions and conditions["classification"] != classification:
            return False

        # Operation match
        if "operation" in conditions and conditions["operation"] != operation:
            return False

        # Role-based conditions
        if "max_role" in conditions:
            max_role = conditions["max_role"]
            actor_rank = _ROLE_RANK.get(actor_role, 999)
            max_rank = _ROLE_RANK.get(max_role, 999)
            if actor_rank < max_rank:
                return False  # Actor is more privileged than max, so rule doesn't apply

        if "min_role" in conditions:
            min_role = conditions["min_role"]
            actor_rank = _ROLE_RANK.get(actor_role, 999)
            min_rank = _ROLE_RANK.get(min_role, 999)
            if actor_rank > min_rank:
                return False  # Actor is less privileged than min

        # ABAC attribute conditions — exact match for string attributes
        for abac_key in _ABAC_STRING_CONDITION_KEYS:
            if abac_key in conditions:
                if attrs.get(abac_key) != conditions[abac_key]:
                    return False

        # ABAC numeric threshold conditions
        if "cohort_size_lt" in conditions:
            cohort = attrs.get("cohort_size")
            if cohort is None or cohort >= conditions["cohort_size_lt"]:
                return False

        if "cohort_size_gte" in conditions:
            cohort = attrs.get("cohort_size")
            if cohort is None or cohort < conditions["cohort_size_gte"]:
                return False

        return True

    async def _ensure_cache(self) -> None:
        """Load policies into in-memory cache if TTL expired.

        Uses an asyncio.Lock to prevent thundering herd on cache refresh.
        """
        global _policy_cache, _cache_loaded_at
        now = time.monotonic()
        if now - _cache_loaded_at < _CACHE_TTL_SECONDS and _policy_cache:
            return

        async with _cache_lock:
            # Double-check after acquiring lock (another coroutine may have refreshed)
            now = time.monotonic()
            if now - _cache_loaded_at < _CACHE_TTL_SECONDS and _policy_cache:
                return

            result = await self._session.execute(
                select(PDPPolicy)
                .where(PDPPolicy.is_active.is_(True))
                .order_by(PDPPolicy.priority)
            )
            policies = result.scalars().all()

            _policy_cache = [
                {
                    "id": p.id,
                    "name": p.name,
                    "conditions_json": p.conditions_json,
                    "decision": p.decision.value if hasattr(p.decision, "value") else p.decision,
                    "obligations_json": p.obligations_json,
                    "reason": p.reason,
                    "priority": p.priority,
                }
                for p in policies
            ]
            _cache_loaded_at = now
            logger.debug("PDP policy cache refreshed: %d policies loaded", len(_policy_cache))

    # Allowed keys for conditions_json validation (SEC-2)
    ALLOWED_CONDITION_KEYS = {
        # RBAC
        "classification",
        "operation",
        "min_role",
        "max_role",
        # ABAC string attributes
        "department",
        "cost_center",
        "data_residency",
        "evidence_type",
        "identity_posture",
        "export_mode",
        # ABAC numeric thresholds
        "cohort_size_lt",
        "cohort_size_gte",
    }

    async def create_rule(
        self,
        *,
        name: str,
        description: str | None = None,
        conditions_json: dict,
        decision: PDPDecisionType,
        obligations_json: list | None = None,
        reason: str | None = None,
        priority: int = 100,
    ) -> PDPPolicy:
        """Create a new policy rule (hot-reloaded on next cache refresh).

        Args:
            name: Unique policy name.
            description: Human-readable description.
            conditions_json: Matching conditions dict (keys must be in ALLOWED_CONDITION_KEYS).
            decision: PERMIT or DENY.
            obligations_json: Optional list of obligations.
            reason: Reason string.
            priority: Evaluation priority (lower = first).

        Returns:
            Created PDPPolicy.

        Raises:
            ValueError: If conditions_json contains unknown keys.
        """
        self._validate_conditions(conditions_json)
        policy = PDPPolicy(
            id=uuid.uuid4(),
            name=name,
            description=description,
            conditions_json=conditions_json,
            decision=decision,
            obligations_json=obligations_json,
            reason=reason,
            priority=priority,
            is_active=True,
            created_at=datetime.now(UTC),
        )
        self._session.add(policy)
        await self._session.flush()

        # Invalidate cache so next evaluation picks up the new rule
        self._invalidate_cache()

        return policy

    async def list_rules(self) -> list[PDPPolicy]:
        """List all active policy rules ordered by priority."""
        result = await self._session.execute(
            select(PDPPolicy)
            .where(PDPPolicy.is_active.is_(True))
            .order_by(PDPPolicy.priority)
        )
        return list(result.scalars().all())

    async def publish_bundle(
        self,
        *,
        version: str,
        name: str,
        published_by: str,
    ) -> PDPPolicyBundle:
        """Create and activate a new policy bundle version.

        Deactivates all previous bundles and activates the new one.
        Agents should compare their cached bundle version against the
        active bundle on each heartbeat to detect drift.

        Args:
            version: Semantic or CalVer version string (e.g. "2026.03.001").
            name: Human-readable bundle name.
            published_by: Identity of the publisher.

        Returns:
            The newly created and activated PDPPolicyBundle.
        """
        # Deactivate all current bundles
        existing = await self._session.execute(
            select(PDPPolicyBundle).where(PDPPolicyBundle.is_active.is_(True))
        )
        for bundle in existing.scalars().all():
            bundle.is_active = False

        now = datetime.now(UTC)
        new_bundle = PDPPolicyBundle(
            id=uuid.uuid4(),
            version=version,
            name=name,
            is_active=True,
            published_at=now,
            published_by=published_by,
            created_at=now,
        )
        self._session.add(new_bundle)
        await self._session.flush()
        return new_bundle

    async def get_active_bundle(self) -> PDPPolicyBundle | None:
        """Return the currently active policy bundle, or None if none published."""
        result = await self._session.execute(
            select(PDPPolicyBundle)
            .where(PDPPolicyBundle.is_active.is_(True))
            .order_by(PDPPolicyBundle.published_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @classmethod
    def _validate_conditions(cls, conditions: dict) -> None:
        """Validate that conditions_json only uses allowed keys.

        Raises:
            ValueError: If unknown keys are found.
        """
        unknown = set(conditions.keys()) - cls.ALLOWED_CONDITION_KEYS
        if unknown:
            raise ValueError(
                f"Unknown condition keys: {sorted(unknown)}. "
                f"Allowed: {sorted(cls.ALLOWED_CONDITION_KEYS)}"
            )

    @staticmethod
    def _invalidate_cache() -> None:
        """Force cache refresh on next evaluation."""
        global _cache_loaded_at
        _cache_loaded_at = 0.0

    @staticmethod
    def get_health_metrics() -> dict[str, Any]:
        """Return PDP health metrics including p99 latency."""
        latencies = list(_recent_latencies)
        if not latencies:
            return {
                "status": "healthy",
                "decisions_tracked": 0,
                "p99_latency_ms": 0.0,
            }

        latencies.sort()
        p99_idx = max(0, int(len(latencies) * 0.99) - 1)
        return {
            "status": "healthy",
            "decisions_tracked": len(latencies),
            "p99_latency_ms": round(latencies[p99_idx], 2),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
        }
