"""Policy Decision Point (PDP) service for access decisions.

Evaluates policy rules against request context (user role, data
classification, engagement scope, operation) and returns structured
PERMIT/DENY decisions with optional obligations.
"""

from __future__ import annotations

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
_CACHE_TTL_SECONDS = 30.0

# Latency tracking for health endpoint
_recent_latencies: collections.deque[float] = collections.deque(maxlen=100)


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

        # Evaluate policies in priority order (lowest number first)
        for policy in _policy_cache:
            if self._matches(policy, actor_role=actor_role, classification=classification, operation=operation):
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
    ) -> bool:
        """Check if a policy's conditions match the request context."""
        conditions = policy.get("conditions_json", {})

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

        return True

    async def _ensure_cache(self) -> None:
        """Load policies into in-memory cache if TTL expired."""
        global _policy_cache, _cache_loaded_at
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
            conditions_json: Matching conditions dict.
            decision: PERMIT or DENY.
            obligations_json: Optional list of obligations.
            reason: Reason string.
            priority: Evaluation priority (lower = first).

        Returns:
            Created PDPPolicy.
        """
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
