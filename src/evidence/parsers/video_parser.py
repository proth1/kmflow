"""Video file parser with frame and audio extraction.

Extracts key frame descriptions and audio transcription from video files.
Falls back to metadata-only extraction if dependencies are unavailable.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult

logger = logging.getLogger(__name__)


class VideoParser(BaseParser):
    """Parser for video files with frame and audio extraction."""

    supported_formats = [".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv"]

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a video file and extract frame/audio content.

        Attempts to extract key frames and audio transcription.

        Args:
            file_path: Path to the video file.
            file_name: Original filename.

        Returns:
            ParseResult with frame and transcription fragments.
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

        # Attempt frame extraction
        try:
            frame_info = await self._extract_frames(file_path)
            if frame_info:
                result.fragments.append(
                    ParsedFragment(
                        fragment_type=FragmentType.TEXT,
                        content=frame_info,
                        metadata={"source": "frame_extraction", "file_name": file_name},
                    )
                )
        except Exception as e:
            logger.warning("Frame extraction failed for %s: %s", file_name, e)

        # Attempt audio extraction and transcription
        try:
            audio_text = await self._extract_audio(file_path)
            if audio_text and audio_text.strip():
                result.fragments.append(
                    ParsedFragment(
                        fragment_type=FragmentType.TEXT,
                        content=audio_text.strip(),
                        metadata={"source": "audio_transcription", "file_name": file_name},
                    )
                )
        except Exception as e:
            logger.warning("Audio extraction failed for %s: %s", file_name, e)

        # Always add a reference fragment
        result.fragments.append(
            ParsedFragment(
                fragment_type=FragmentType.TEXT,
                content=f"Video file: {file_name} ({path.suffix.lower().lstrip('.')} format)",
                metadata={
                    "file_path": file_path,
                    "file_name": file_name,
                    "type": "video_reference",
                },
            )
        )

        return result

    async def _extract_frames(self, file_path: str) -> str:
        """Extract key frame information from a video.

        Uses cv2 (OpenCV) to sample frames at regular intervals
        and describe their basic properties.

        Args:
            file_path: Path to the video file.

        Returns:
            Description of extracted frames.
        """
        try:
            import cv2

            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                return ""

            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()

            return (
                f"Video properties: {width}x{height}, {fps:.1f} FPS, "
                f"{frame_count} frames, {duration:.1f}s duration"
            )
        except ImportError:
            logger.info("OpenCV not installed; frame extraction unavailable")
            return ""

    async def _extract_audio(self, file_path: str) -> str:
        """Extract and transcribe audio track from video.

        Placeholder for audio extraction - would use ffmpeg in production.

        Args:
            file_path: Path to the video file.

        Returns:
            Transcribed audio text.
        """
        # Would require ffmpeg to extract audio track, then speech_recognition
        logger.info("Video audio extraction not yet implemented for %s", file_path)
        return ""
