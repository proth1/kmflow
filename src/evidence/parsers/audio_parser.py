"""Audio file parser with transcription support.

Extracts transcription text from audio files (MP3, WAV, M4A, OGG).
Falls back to metadata-only extraction if transcription is unavailable.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult

logger = logging.getLogger(__name__)


class AudioParser(BaseParser):
    """Parser for audio files with transcription extraction."""

    supported_formats = [".mp3", ".wav", ".m4a", ".ogg", ".flac", ".wma"]

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse an audio file and extract transcription.

        Attempts transcription using speech_recognition if available,
        otherwise returns metadata-only fragments.

        Args:
            file_path: Path to the audio file.
            file_name: Original filename.

        Returns:
            ParseResult with transcription fragments and audio metadata.
        """
        result = ParseResult()
        path = Path(file_path)

        if not path.exists():
            result.error = f"File not found: {file_path}"
            return result

        stat = path.stat()
        result.metadata = {
            "file_name": file_name,
            "file_size": stat.st_size,
            "format": path.suffix.lower().lstrip("."),
        }

        # Attempt transcription
        try:
            text = await self._transcribe(file_path)
            if text and text.strip():
                result.fragments.append(
                    ParsedFragment(
                        fragment_type=FragmentType.TEXT,
                        content=text.strip(),
                        metadata={"source": "transcription", "file_name": file_name},
                    )
                )
        except Exception as e:  # Intentionally broad: parser library exceptions vary by format
            logger.warning("Transcription failed for %s: %s", file_name, e)
            result.error = f"Transcription failed: {e}"

        # Always add a reference fragment
        result.fragments.append(
            ParsedFragment(
                fragment_type=FragmentType.TEXT,
                content=f"Audio file: {file_name} ({path.suffix.lower().lstrip('.')} format)",
                metadata={
                    "file_path": file_path,
                    "file_name": file_name,
                    "type": "audio_reference",
                },
            )
        )

        return result

    async def _transcribe(self, file_path: str) -> str:
        """Transcribe audio to text.

        Uses speech_recognition with Google Web Speech API if available.

        Args:
            file_path: Path to the audio file.

        Returns:
            Transcribed text string.
        """
        try:
            import speech_recognition as sr

            recognizer = sr.Recognizer()
            with sr.AudioFile(file_path) as source:
                audio = recognizer.record(source)
            text = recognizer.recognize_google(audio)
            return text
        except ImportError:
            logger.info("speech_recognition not installed; transcription unavailable")
            return ""
        except Exception as e:  # Intentionally broad: parser library exceptions vary by format
            logger.warning("Transcription error: %s", e)
            return ""
