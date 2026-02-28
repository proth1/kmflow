"""Watermark extraction utility for forensic document recovery (Story #387).

Extracts invisible watermarks from exported documents and queries the
export log to recover the full chain of custody.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.security.watermark.service import WatermarkService

logger = logging.getLogger(__name__)

# Pattern to extract base64 watermark from HTML meta tag
_HTML_WATERMARK_PATTERN = re.compile(r'<meta\s+name="kmflow-watermark"\s+content="([^"]+)"')


class WatermarkExtractor:
    """Extracts and verifies watermarks from exported documents."""

    def __init__(self, session: AsyncSession) -> None:
        self._service = WatermarkService(session)
        self._session = session

    async def extract_from_encoded(self, encoded_watermark: str) -> dict[str, Any] | None:
        """Extract and verify a raw base64-encoded watermark string.

        Returns decoded payload with export log metadata if found, None if
        the watermark is invalid or tampered.
        """
        decoded = self._service.decode_invisible_watermark(encoded_watermark)
        if decoded is None:
            return None

        export_id = decoded.get("export_id")
        if not export_id:
            return None

        try:
            export_uuid = uuid.UUID(export_id)
        except ValueError:
            logger.warning("Invalid export_id in watermark: %s", export_id)
            return None

        log_entry = await self._service.lookup_by_export_id(export_uuid)

        return {
            "watermark": decoded,
            "export_log": log_entry,
            "verified": True,
        }

    async def extract_from_html(self, html_content: str) -> dict[str, Any] | None:
        """Extract watermark from an HTML document's meta tag.

        Searches for <meta name="kmflow-watermark" content="..."> and decodes it.
        """
        match = _HTML_WATERMARK_PATTERN.search(html_content)
        if not match:
            logger.info("No kmflow-watermark meta tag found in HTML")
            return None

        return await self.extract_from_encoded(match.group(1))
