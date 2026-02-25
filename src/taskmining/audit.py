"""Task mining audit logging: immutable audit trail for all sensitive operations.

Provides insert-only logging for agent lifecycle events, PII detection/quarantine,
consent changes, and capture start/stop. Audit records are exempt from data
retention cleanup (7-year compliance hold per PRD Section 7.5).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.audit import AuditAction, AuditLog

logger = logging.getLogger(__name__)


class TaskMiningAuditLogger:
    """Insert-only audit logger for task mining operations.

    All methods create immutable AuditLog records. No update or delete
    operations are exposed — audit records are append-only by design.
    """

    async def log(
        self,
        session: AsyncSession,
        event_type: AuditAction,
        agent_id: UUID,
        engagement_id: UUID | None = None,
        actor: str = "system",
        **kwargs: object,
    ) -> AuditLog | None:
        """Write a single audit log entry.

        Returns None if engagement_id is not available (logs to structured
        logger instead for SIEM ingestion).
        """
        details = {"agent_id": str(agent_id)}
        for key, value in kwargs.items():
            details[key] = str(value) if isinstance(value, UUID) else value

        detail_str = json.dumps(details, default=str)

        if engagement_id is None:
            logger.warning(
                "TASK_MINING_AUDIT event=%s agent=%s details=%s",
                event_type.value,
                agent_id,
                detail_str,
            )
            return None

        audit = AuditLog(
            engagement_id=engagement_id,
            action=event_type,
            actor=actor,
            details=detail_str,
        )
        session.add(audit)
        return audit

    async def log_agent_approved(
        self,
        session: AsyncSession,
        agent_id: UUID,
        engagement_id: UUID,
        approved_by: str,
    ) -> AuditLog | None:
        return await self.log(
            session,
            AuditAction.AGENT_APPROVED,
            agent_id,
            engagement_id=engagement_id,
            actor=approved_by,
            approved_by=approved_by,
        )

    async def log_agent_revoked(
        self,
        session: AsyncSession,
        agent_id: UUID,
        engagement_id: UUID,
        revoked_by: str,
    ) -> AuditLog | None:
        return await self.log(
            session,
            AuditAction.AGENT_REVOKED,
            agent_id,
            engagement_id=engagement_id,
            actor=revoked_by,
            revoked_by=revoked_by,
        )

    async def log_consent_granted(
        self,
        session: AsyncSession,
        agent_id: UUID,
        engagement_id: UUID,
        consent_type: str,
        capture_mode: str,
    ) -> AuditLog | None:
        return await self.log(
            session,
            AuditAction.AGENT_CONSENT_GRANTED,
            agent_id,
            engagement_id=engagement_id,
            consent_type=consent_type,
            capture_mode=capture_mode,
        )

    async def log_consent_revoked(
        self,
        session: AsyncSession,
        agent_id: UUID,
        engagement_id: UUID,
    ) -> AuditLog | None:
        return await self.log(
            session,
            AuditAction.AGENT_CONSENT_REVOKED,
            agent_id,
            engagement_id=engagement_id,
        )

    async def log_pii_quarantined(
        self,
        session: AsyncSession,
        agent_id: UUID,
        engagement_id: UUID,
        quarantine_id: UUID,
        pii_type: str,
        detection_method: str = "regex_l3",
    ) -> AuditLog | None:
        return await self.log(
            session,
            AuditAction.PII_QUARANTINED,
            agent_id,
            engagement_id=engagement_id,
            quarantine_id=quarantine_id,
            pii_type=pii_type,
            detection_method=detection_method,
        )

    async def log_quarantine_auto_deleted(
        self,
        session: AsyncSession,
        engagement_id: UUID | None,
        rows_deleted: int,
        duration_ms: float,
    ) -> AuditLog | None:
        """Log a quarantine auto-cleanup run.

        Uses a sentinel UUID for agent_id since this is a system-level job.
        """
        sentinel = UUID("00000000-0000-0000-0000-000000000000")
        return await self.log(
            session,
            AuditAction.PII_QUARANTINE_AUTO_DELETED,
            sentinel,
            engagement_id=engagement_id,
            rows_deleted=rows_deleted,
            duration_ms=duration_ms,
            run_at=datetime.now(timezone.utc).isoformat(),
        )

    async def log_capture_started(
        self,
        session: AsyncSession,
        agent_id: UUID,
        engagement_id: UUID,
        session_id: UUID,
    ) -> AuditLog | None:
        return await self.log(
            session,
            AuditAction.TASK_MINING_STARTED,
            agent_id,
            engagement_id=engagement_id,
            session_id=session_id,
        )

    async def log_capture_stopped(
        self,
        session: AsyncSession,
        agent_id: UUID,
        engagement_id: UUID,
        session_id: UUID,
        event_count: int = 0,
        duration_seconds: float = 0.0,
    ) -> AuditLog | None:
        return await self.log(
            session,
            AuditAction.TASK_MINING_STOPPED,
            agent_id,
            engagement_id=engagement_id,
            session_id=session_id,
            event_count=event_count,
            duration_seconds=duration_seconds,
        )
