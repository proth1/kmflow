"""VCE record dataclass — the unit of data buffered and uploaded to the backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class VCERecord:
    """Metadata record for a single visual context event.

    Contains only classification results and redacted context — no pixel data.
    """

    timestamp: datetime
    screen_state_class: str
    confidence: float
    trigger_reason: str
    application_name: str
    dwell_ms: int

    # Optional fields
    system_guess: str | None = None
    module_guess: str | None = None
    sensitivity_flags: list[str] = field(default_factory=list)
    window_title_redacted: str | None = None
    interaction_intensity: float | None = None
    snapshot_ref: str | None = None
    ocr_text_redacted: str | None = None
    classification_method: str | None = None

    def to_dict(self) -> dict:
        """Serialise to a dict suitable for JSON upload."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "screen_state_class": self.screen_state_class,
            "confidence": self.confidence,
            "trigger_reason": self.trigger_reason,
            "application_name": self.application_name,
            "dwell_ms": self.dwell_ms,
            "system_guess": self.system_guess,
            "module_guess": self.module_guess,
            "sensitivity_flags": self.sensitivity_flags,
            "window_title_redacted": self.window_title_redacted,
            "interaction_intensity": self.interaction_intensity,
            "snapshot_ref": self.snapshot_ref,
            "ocr_text_redacted": self.ocr_text_redacted,
            "classification_method": self.classification_method,
        }
