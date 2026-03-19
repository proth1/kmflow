"""Evidence domain exceptions.

Domain-specific exceptions for the evidence processing pipeline.
These are caught at the API boundary and translated to HTTP responses.
"""

from __future__ import annotations


class EvidenceValidationError(ValueError):
    """Raised when evidence fails validation (file type, size, etc.).

    Attributes:
        status_hint: Suggested HTTP status code for the API layer.
    """

    def __init__(self, message: str, *, status_hint: int = 400) -> None:
        super().__init__(message)
        self.status_hint = status_hint
