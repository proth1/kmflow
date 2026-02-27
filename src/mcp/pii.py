"""PII masking utilities for MCP logging.

Provides a helper to redact email addresses and names from log data
to prevent accidental PII exposure in log streams.
"""

from __future__ import annotations

import re


# Email pattern: matches common email formats
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def mask_pii(data: str) -> str:
    """Replace PII patterns in a string with masked values.

    Currently masks:
    - Email addresses -> ***@***.***

    Args:
        data: The string to mask.

    Returns:
        The masked string.
    """
    return _EMAIL_RE.sub("***@***.***", data)
