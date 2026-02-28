"""SAP timestamp conversion utilities (Story #330).

Converts SAP-native date/time formats to ISO 8601 UTC:
- DATS (YYYYMMDD) + TIMS (HHMMSS) → ISO 8601 datetime
- SAP OData Edm.DateTime ``/Date(milliseconds)/`` → ISO 8601
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

# Pattern for SAP OData Edm.DateTime: /Date(1234567890000)/
_ODATA_DATE_PATTERN = re.compile(r"^/Date\((\d+)\)/$")


def dats_tims_to_iso(dats: str, tims: str = "000000") -> str:
    """Convert SAP DATS+TIMS to ISO 8601 UTC string.

    Args:
        dats: SAP date in YYYYMMDD format (8 chars).
        tims: SAP time in HHMMSS format (6 chars, default midnight).

    Returns:
        ISO 8601 UTC datetime string (e.g., "2026-01-15T09:30:00Z").

    Raises:
        ValueError: If dats/tims format is invalid.
    """
    if len(dats) != 8 or not dats.isdigit():
        msg = f"Invalid SAP DATS format: {dats!r} (expected YYYYMMDD)"
        raise ValueError(msg)

    tims = tims or "000000"
    if len(tims) != 6 or not tims.isdigit():
        msg = f"Invalid SAP TIMS format: {tims!r} (expected HHMMSS)"
        raise ValueError(msg)

    dt = datetime(
        year=int(dats[:4]),
        month=int(dats[4:6]),
        day=int(dats[6:8]),
        hour=int(tims[:2]),
        minute=int(tims[2:4]),
        second=int(tims[4:6]),
        tzinfo=UTC,
    )
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def odata_datetime_to_iso(odata_value: str) -> str:
    """Convert SAP OData Edm.DateTime to ISO 8601 UTC string.

    Args:
        odata_value: OData date like ``/Date(1706000000000)/``.

    Returns:
        ISO 8601 UTC datetime string.

    Raises:
        ValueError: If format doesn't match OData pattern.
    """
    match = _ODATA_DATE_PATTERN.match(odata_value)
    if not match:
        msg = f"Invalid OData DateTime format: {odata_value!r}"
        raise ValueError(msg)

    millis = int(match.group(1))
    dt = datetime.fromtimestamp(millis / 1000, tz=UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_sap_timestamp(value: str) -> str:
    """Normalize any SAP timestamp format to ISO 8601.

    Detects the format and converts accordingly:
    - ``/Date(...)/ `` → OData Edm.DateTime
    - ``YYYYMMDD`` (8 digits) → SAP DATS
    - Already ISO 8601 → returned as-is

    Args:
        value: SAP timestamp in any supported format.

    Returns:
        ISO 8601 UTC datetime string.
    """
    if value.startswith("/Date("):
        return odata_datetime_to_iso(value)

    if len(value) == 8 and value.isdigit():
        return dats_tims_to_iso(value)

    if len(value) == 14 and value.isdigit():
        # YYYYMMDDHHMMSS combined format
        return dats_tims_to_iso(value[:8], value[8:])

    # Assume already ISO 8601
    return value
