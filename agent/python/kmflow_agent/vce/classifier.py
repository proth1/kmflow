"""VCE screen state classifier: rule-based, VLM stub, and hybrid.

Classification produces a (ScreenStateClass, confidence, method) tuple.
Phase 1 ships rule-based only. The VLMClassifier is a placeholder for
future Florence-2 / Moondream2 integration.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Screen state class values — mirrors ScreenStateClass enum in the backend
QUEUE = "queue"
SEARCH = "search"
DATA_ENTRY = "data_entry"
REVIEW = "review"
ERROR = "error"
WAITING_LATENCY = "waiting_latency"
NAVIGATION = "navigation"
OTHER = "other"

# ---------------------------------------------------------------------------
# Keyword patterns for rule-based classification
# ---------------------------------------------------------------------------

_ERROR_KEYWORDS = re.compile(
    r"\b(error|exception|failed|failure|invalid|not found|denied|forbidden|timeout|crash)\b",
    re.IGNORECASE,
)
_SEARCH_KEYWORDS = re.compile(
    r"\b(search|find|filter|results|query|lookup|no results)\b",
    re.IGNORECASE,
)
_QUEUE_KEYWORDS = re.compile(
    r"\b(queue|inbox|pending|backlog|worklist|workqueue|work list|unassigned|waiting)\b",
    re.IGNORECASE,
)
_DATA_ENTRY_KEYWORDS = re.compile(
    r"\b(enter|input|form|submit|save|create|new|add|edit|update|required field)\b",
    re.IGNORECASE,
)
_REVIEW_KEYWORDS = re.compile(
    r"\b(review|approve|reject|confirm|verify|check|validate|decision|authorise|authorize)\b",
    re.IGNORECASE,
)
_WAITING_KEYWORDS = re.compile(
    r"\b(loading|please wait|processing|saving|uploading|downloading|connecting)\b",
    re.IGNORECASE,
)
_NAVIGATION_KEYWORDS = re.compile(
    r"\b(home|dashboard|menu|navigate|back|forward|previous|next|step \d|page \d)\b",
    re.IGNORECASE,
)

# Minimum confidence for rule-based classification
_HIGH_CONFIDENCE = 0.80
_MEDIUM_CONFIDENCE = 0.65
_LOW_CONFIDENCE = 0.40


class RuleBasedClassifier:
    """Classify screen state using keyword matching and interaction heuristics."""

    def classify(
        self,
        ocr_text: str,
        window_title: str,
        app_name: str,
        interaction_intensity: float,
        dwell_ms: int,
    ) -> tuple[str, float]:
        """Return (screen_state_class, confidence).

        Args:
            ocr_text: PII-redacted OCR text from the screen.
            window_title: Redacted window title.
            app_name: Application name.
            interaction_intensity: Events-per-second during dwell period.
            dwell_ms: Observed dwell time in milliseconds.

        Returns:
            Tuple of (screen_state_class value, confidence in [0.0, 1.0]).
        """
        combined = f"{window_title} {ocr_text}".strip()

        # Priority order: error > waiting > queue > search > data_entry > review > navigation > other
        if _ERROR_KEYWORDS.search(combined):
            return ERROR, _HIGH_CONFIDENCE

        if _WAITING_KEYWORDS.search(combined):
            # Corroborate with low interaction intensity
            if interaction_intensity < 0.5:
                return WAITING_LATENCY, _HIGH_CONFIDENCE
            return WAITING_LATENCY, _MEDIUM_CONFIDENCE

        if _QUEUE_KEYWORDS.search(combined):
            return QUEUE, _HIGH_CONFIDENCE

        if _SEARCH_KEYWORDS.search(combined):
            return SEARCH, _HIGH_CONFIDENCE

        if _DATA_ENTRY_KEYWORDS.search(combined):
            # High interaction intensity suggests active typing → data entry
            if interaction_intensity > 1.0:
                return DATA_ENTRY, _HIGH_CONFIDENCE
            return DATA_ENTRY, _MEDIUM_CONFIDENCE

        if _REVIEW_KEYWORDS.search(combined):
            return REVIEW, _HIGH_CONFIDENCE

        if _NAVIGATION_KEYWORDS.search(combined):
            return NAVIGATION, _MEDIUM_CONFIDENCE

        # Heuristic fall-back based on dwell + interaction intensity
        if dwell_ms > 10_000 and interaction_intensity < 0.1:
            # Long dwell, almost no interaction — likely waiting
            return WAITING_LATENCY, _MEDIUM_CONFIDENCE

        if dwell_ms > 5_000 and interaction_intensity > 2.0:
            # Long dwell, high interaction — likely data entry
            return DATA_ENTRY, _LOW_CONFIDENCE

        return OTHER, _LOW_CONFIDENCE


class VLMClassifier:
    """Placeholder for Phase 2 VLM-based screen state classification.

    Will integrate Florence-2 or Moondream2 for vision-language model
    inference. Returns (OTHER, 0.0) until the model is integrated.
    """

    def classify(self, image_bytes: bytes) -> tuple[str, float]:
        """Return (screen_state_class, confidence).

        Phase 2 stub — always returns (OTHER, 0.0).
        """
        logger.debug("VLMClassifier.classify called (stub — returning OTHER, 0.0)")
        return OTHER, 0.0


class HybridClassifier:
    """Runs rule-based and VLM classifiers, returns the higher-confidence result."""

    def __init__(self) -> None:
        self._rule_based = RuleBasedClassifier()
        self._vlm = VLMClassifier()

    def classify(
        self,
        ocr_text: str,
        window_title: str,
        app_name: str,
        interaction_intensity: float,
        dwell_ms: int,
        image_bytes: bytes | None = None,
    ) -> tuple[str, float, str]:
        """Run both classifiers and return the result with the highest confidence.

        Args:
            ocr_text: PII-redacted OCR output.
            window_title: Redacted window title.
            app_name: Application name.
            interaction_intensity: Events/second during dwell.
            dwell_ms: Dwell time in milliseconds.
            image_bytes: Optional raw PNG bytes for VLM (ignored in Phase 1).

        Returns:
            Tuple of (screen_state_class, confidence, classification_method).
            classification_method is one of "rule_based", "vlm", or "hybrid".
        """
        rb_class, rb_conf = self._rule_based.classify(
            ocr_text=ocr_text,
            window_title=window_title,
            app_name=app_name,
            interaction_intensity=interaction_intensity,
            dwell_ms=dwell_ms,
        )

        vlm_class, vlm_conf = (OTHER, 0.0)
        if image_bytes:
            vlm_class, vlm_conf = self._vlm.classify(image_bytes)

        if vlm_conf > rb_conf:
            return vlm_class, vlm_conf, "vlm"

        return rb_class, rb_conf, "rule_based"
