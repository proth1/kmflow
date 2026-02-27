"""Watermark service for export document tracking (Story #387).

Provides visible and invisible watermarking for PDF and HTML exports.
Invisible watermarks use HMAC-SHA256 signed payloads for tamper detection.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.models.export_log import ExportLog

logger = logging.getLogger(__name__)

# Delimiter for watermark payload fields
_PAYLOAD_DELIMITER = "|"


class WatermarkService:
    """Manages watermark generation, embedding, and export logging."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._secret_key = get_settings().jwt_secret_key.encode("utf-8")

    def generate_visible_watermark(
        self,
        engagement_name: str,
        export_date: datetime | None = None,
    ) -> str:
        """Generate visible watermark text for PDF/HTML header overlay.

        Returns a string like 'ACME Corp Engagement — Exported 2026-02-27'.
        """
        date = export_date or datetime.now(UTC)
        return f"{engagement_name} — Exported {date.strftime('%Y-%m-%d')}"

    def encode_invisible_watermark(
        self,
        user_id: uuid.UUID,
        export_id: uuid.UUID,
        timestamp: datetime | None = None,
    ) -> str:
        """Encode an invisible watermark payload with HMAC-SHA256 signature.

        Format: base64(user_id|export_id|timestamp|hmac_signature)
        The HMAC covers user_id|export_id|timestamp to detect tampering.
        """
        ts = timestamp or datetime.now(UTC)
        payload = _PAYLOAD_DELIMITER.join([
            str(user_id),
            str(export_id),
            ts.isoformat(),
        ])

        signature = hmac.new(
            self._secret_key, payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        signed_payload = f"{payload}{_PAYLOAD_DELIMITER}{signature}"
        return base64.b64encode(signed_payload.encode("utf-8")).decode("ascii")

    def decode_invisible_watermark(
        self, encoded: str
    ) -> dict[str, Any] | None:
        """Decode and verify an invisible watermark.

        Returns dict with user_id, export_id, timestamp if valid, None if tampered.
        """
        try:
            decoded = base64.b64decode(encoded.encode("ascii")).decode("utf-8")
        except Exception:
            logger.warning("Failed to base64-decode watermark")
            return None

        parts = decoded.split(_PAYLOAD_DELIMITER)
        if len(parts) != 4:
            logger.warning("Watermark has unexpected number of fields: %d", len(parts))
            return None

        user_id_str, export_id_str, timestamp_str, signature = parts

        # Verify HMAC
        payload = _PAYLOAD_DELIMITER.join([user_id_str, export_id_str, timestamp_str])
        expected_sig = hmac.new(
            self._secret_key, payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            logger.warning("Watermark HMAC verification failed — possible tampering")
            return None

        return {
            "user_id": user_id_str,
            "export_id": export_id_str,
            "timestamp": timestamp_str,
        }

    def generate_html_watermark_meta(
        self,
        export_id: uuid.UUID,
        engagement_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> str:
        """Generate hidden HTML meta element for watermark embedding.

        Returns an HTML string with watermark data as a hidden element.
        """
        encoded = self.encode_invisible_watermark(user_id, export_id)
        return (
            f'<meta name="kmflow-watermark" '
            f'content="{encoded}" '
            f'data-export-id="{export_id}" '
            f'data-engagement-id="{engagement_id}" />'
        )

    async def create_export_log(
        self,
        *,
        export_id: uuid.UUID,
        recipient_id: uuid.UUID,
        document_type: str,
        engagement_id: uuid.UUID,
    ) -> ExportLog:
        """Create an append-only export log entry.

        Records who received what document and when for forensic tracking.
        """
        entry = ExportLog(
            id=export_id,
            recipient_id=recipient_id,
            document_type=document_type,
            engagement_id=engagement_id,
        )
        self._session.add(entry)
        await self._session.flush()
        await self._session.commit()
        return entry

    async def get_export_logs(
        self,
        engagement_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get paginated export logs for an engagement."""
        from sqlalchemy import func as sa_func

        count_result = await self._session.execute(
            select(sa_func.count()).where(
                ExportLog.engagement_id == engagement_id,
            )
        )
        total = count_result.scalar() or 0

        result = await self._session.execute(
            select(ExportLog)
            .where(ExportLog.engagement_id == engagement_id)
            .order_by(ExportLog.exported_at.desc())
            .limit(limit)
            .offset(offset)
        )
        logs = result.scalars().all()

        return {
            "items": [
                {
                    "export_id": str(log.id),
                    "recipient_id": str(log.recipient_id),
                    "document_type": log.document_type,
                    "engagement_id": str(log.engagement_id),
                    "exported_at": log.exported_at.isoformat(),
                }
                for log in logs
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def lookup_by_export_id(
        self, export_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Look up export log entry by export_id for forensic recovery."""
        result = await self._session.execute(
            select(ExportLog).where(ExportLog.id == export_id)
        )
        log = result.scalar_one_or_none()
        if log is None:
            return None
        return {
            "export_id": str(log.id),
            "recipient_id": str(log.recipient_id),
            "document_type": log.document_type,
            "engagement_id": str(log.engagement_id),
            "exported_at": log.exported_at.isoformat(),
        }
