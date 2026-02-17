"""Monitoring configuration validation.

Validates monitoring job configuration including schedule format,
source type requirements, and connection references.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.core.models import MonitoringSourceType

logger = logging.getLogger(__name__)

CRON_PATTERN = re.compile(
    r"^(\*|[0-9,\-/]+)\s+"
    r"(\*|[0-9,\-/]+)\s+"
    r"(\*|[0-9,\-/]+)\s+"
    r"(\*|[0-9,\-/]+)\s+"
    r"(\*|[0-9,\-/]+)$"
)


def validate_cron_expression(cron: str) -> bool:
    """Validate a cron expression (5-field format)."""
    return bool(CRON_PATTERN.match(cron.strip()))


def validate_monitoring_config(
    source_type: MonitoringSourceType,
    config: dict[str, Any] | None,
) -> list[str]:
    """Validate monitoring job configuration for a source type.

    Args:
        source_type: The type of monitoring source.
        config: The configuration dict to validate.

    Returns:
        List of validation error messages (empty if valid).
    """
    errors: list[str] = []
    config = config or {}

    if source_type == MonitoringSourceType.EVENT_LOG:
        if not config.get("log_source"):
            errors.append("event_log source requires 'log_source' in config")
    elif source_type == MonitoringSourceType.SYSTEM_API:
        if not config.get("endpoint_url"):
            errors.append("system_api source requires 'endpoint_url' in config")
    elif source_type == MonitoringSourceType.FILE_WATCH:
        if not config.get("watch_path"):
            errors.append("file_watch source requires 'watch_path' in config")

    return errors
