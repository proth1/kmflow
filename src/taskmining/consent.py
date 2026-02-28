"""Capture consent management for task mining agents.

Tracks per-agent consent with an immutable audit trail of grants and
revocations. Consent status gates event acceptance — agents with revoked
or missing consent cannot submit events.
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.models.taskmining import AgentStatus, TaskMiningAgent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ConsentType(enum.StrEnum):
    """Context in which consent was obtained."""

    ENGAGEMENT = "engagement"
    ENTERPRISE = "enterprise"


class ConsentStatus(enum.StrEnum):
    """Current consent state for an agent."""

    ACTIVE = "active"
    REVOKED = "revoked"
    NOT_RECORDED = "not_recorded"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class ConsentRecord(Base):
    """Immutable consent record — one row per grant or revocation event."""

    __tablename__ = "consent_records"
    __table_args__ = (
        Index("ix_consent_records_agent_id", "agent_id"),
        Index("ix_consent_records_engagement_id", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_mining_agents.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    consent_type: Mapped[ConsentType] = mapped_column(Enum(ConsentType), nullable=False)
    capture_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="action_level")
    user_acknowledged: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:
        status = "revoked" if self.revoked_at else "active"
        return f"<ConsentRecord(agent_id={self.agent_id}, status={status})>"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ConsentManager:
    """Manages consent lifecycle for task mining agents."""

    # Agents in these statuses may (re-)grant consent
    _CONSENTABLE_STATUSES = {AgentStatus.PENDING_APPROVAL, AgentStatus.REVOKED}

    @staticmethod
    def _hash_ip(ip_address: str, secret: str) -> str:
        """HMAC-SHA256 hash of an IP address, keyed with a server secret."""
        return hmac.new(secret.encode(), ip_address.encode(), hashlib.sha256).hexdigest()

    async def record_consent(
        self,
        session: AsyncSession,
        agent_id: uuid.UUID,
        engagement_id: uuid.UUID,
        consent_type: ConsentType,
        capture_mode: str = "action_level",
        ip_address: str | None = None,
        ip_hash_secret: str = "",
    ) -> ConsentRecord:
        """Record a new consent grant. Transitions agent to APPROVED.

        Args:
            ip_hash_secret: Server-side secret for HMAC IP hashing.
                Pass from settings.jwt_secret_key or equivalent.
        """
        ip_hash = self._hash_ip(ip_address, ip_hash_secret) if ip_address else None

        record = ConsentRecord(
            agent_id=agent_id,
            engagement_id=engagement_id,
            consent_type=consent_type,
            capture_mode=capture_mode,
            user_acknowledged=True,
            ip_address_hash=ip_hash,
        )
        session.add(record)

        # Transition agent status — allow PENDING_APPROVAL and REVOKED agents
        agent = await session.get(TaskMiningAgent, agent_id)
        if agent and agent.status in self._CONSENTABLE_STATUSES:
            agent.status = AgentStatus.APPROVED
            agent.revoked_at = None  # Clear revocation timestamp on re-grant

        logger.info("Consent granted for agent %s (type=%s, mode=%s)", agent_id, consent_type, capture_mode)
        return record

    async def revoke_consent(
        self,
        session: AsyncSession,
        agent_id: uuid.UUID,
    ) -> ConsentRecord | None:
        """Revoke consent for an agent. Transitions agent to REVOKED."""
        # Find the latest active consent
        stmt = (
            select(ConsentRecord)
            .where(ConsentRecord.agent_id == agent_id, ConsentRecord.revoked_at.is_(None))
            .order_by(ConsentRecord.consented_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            logger.warning("No active consent found for agent %s", agent_id)
            return None

        record.revoked_at = datetime.now(UTC)

        # Transition agent status
        agent = await session.get(TaskMiningAgent, agent_id)
        if agent:
            agent.status = AgentStatus.REVOKED
            agent.revoked_at = datetime.now(UTC)

        logger.info("Consent revoked for agent %s", agent_id)
        return record

    async def get_consent_status(
        self,
        session: AsyncSession,
        agent_id: uuid.UUID,
    ) -> ConsentStatus:
        """Check the current consent status for an agent."""
        stmt = (
            select(ConsentRecord)
            .where(ConsentRecord.agent_id == agent_id)
            .order_by(ConsentRecord.consented_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            return ConsentStatus.NOT_RECORDED
        if record.revoked_at is not None:
            return ConsentStatus.REVOKED
        return ConsentStatus.ACTIVE

    async def get_engagement_consent_trail(
        self,
        session: AsyncSession,
        engagement_id: uuid.UUID,
    ) -> list[ConsentRecord]:
        """Get the full consent audit trail for an engagement."""
        stmt = (
            select(ConsentRecord)
            .where(ConsentRecord.engagement_id == engagement_id)
            .order_by(ConsentRecord.consented_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def has_active_consent(
        self,
        session: AsyncSession,
        agent_id: uuid.UUID,
    ) -> bool:
        """Quick check: does this agent have active (non-revoked) consent?"""
        status = await self.get_consent_status(session, agent_id)
        return status == ConsentStatus.ACTIVE
