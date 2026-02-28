"""Language detection for evidence text content.

Uses langdetect library (Google's language detection) to identify the
dominant language of extracted text content, returning ISO 639-1 codes.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def detect_language(text: str) -> str | None:
    """Detect the dominant language of the given text.

    Args:
        text: The text content to analyze.

    Returns:
        ISO 639-1 language code (e.g., "en", "fr", "de")
        or None if detection fails or text is too short.
    """
    if not text or len(text.strip()) < 20:
        return None

    try:
        from langdetect import detect
        from langdetect.lang_detect_exception import LangDetectException

        result = detect(text.strip())
        return str(result)
    except LangDetectException:
        logger.debug("Language detection failed for text of length %d", len(text))
        return None
    except ImportError:
        logger.warning("langdetect not installed; language detection unavailable")
        return None
